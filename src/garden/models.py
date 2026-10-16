import re

from auditlog.registry import auditlog
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class BarcodeManager(models.Manager):
    """Manager that accepts a ``barcode`` in place of a primary key.

    Foreign keys may be given as a barcode string or as a plain integer primary
    key; both are resolved to the related instance.
    """

    def create(self, **kwargs):
        barcode = kwargs.pop('barcode', None)
        if barcode is not None:
            if 'id' in kwargs:
                raise ValueError('Specify either id or barcode, not both.')
            kwargs['id'] = self.model.pk_from_barcode(barcode)
        for field in self.model._meta.fields:
            if not field.is_relation or field.name not in kwargs:
                continue
            value = kwargs[field.name]
            if isinstance(value, int):
                kwargs[field.name] = field.related_model.objects.get(pk=value)
        return super().create(**kwargs)


class BarcodedBase(models.Model):
    barcode_start = 0
    prefix = 'P='
    # Number of digits the id is zero-padded to in the barcode.  Derived from
    # ``barcode_start`` (e.g. 100 -> 3 digits, 1000 -> 4 digits) unless set
    # explicitly on the subclass.
    barcode_width = None

    # Scanning tracking
    last_scanned_at = models.DateTimeField(null=True, blank=True, help_text='When this object was last scanned')

    objects = BarcodeManager()

    class Meta:
        abstract = True

    def mark_scanned(self):
        """Record that this object was just scanned."""
        self.last_scanned_at = timezone.now()
        self.save(update_fields=['last_scanned_at'])

    @classmethod
    def _barcode_width(cls):
        """Return the zero-pad width for this model's barcode ids."""
        if cls.barcode_width is not None:
            return cls.barcode_width
        # ``barcode_start`` marks the first id in the range, so its digit count
        # is the width (e.g. 100 -> 3, 1000 -> 4).  A start of 0 or 1 means a
        # single-digit range, which we pad to 3 for consistency.
        return max(len(str(cls.barcode_start)), 3)

    @property
    def barcode(self):
        # An unsaved instance has no id yet (e.g. a blank admin inline row), so
        # there is no barcode to show.
        if self.id is None:
            return '<unsaved>'
        return f'{self.prefix}{self.id:0{self._barcode_width()}d}'

    @property
    def verbose_name(self):
        """Human-readable model name (e.g. 'plant', 'container')."""
        return self._meta.verbose_name

    @property
    def scan_url(self):
        """URL that shows this object as if its barcode had been scanned."""

        return reverse('scan', query={'barcode': self.barcode})

    @classmethod
    def pk_from_barcode(cls, barcode):
        """Return the primary key encoded in ``barcode`` for this model."""
        return int(barcode.removeprefix(cls.prefix))

    @classmethod
    def from_barcode(cls, barcode):
        """Return the instance matching ``barcode``, or ``None`` if not found.

        The barcode must be of the form ``<prefix><integer>`` for this model.
        """
        match = re.match(f'^{re.escape(cls.prefix)}(\\d+)$', barcode or '')
        if not match:
            return None
        return cls.objects.filter(pk=match.group(1)).first()


class Container(BarcodedBase):
    barcode_start = 1
    prefix = 'PC='

    name = models.CharField(max_length=100)  # Example: 'Blue ribbon 1'

    def __str__(self):
        return f'{self.barcode}: {self.name}'

    @property
    def contents(self):
        """Return the packets and planting events stored in this container.

        Planting events are grouped by their planting, and ordered by date
        within each planting.
        """
        events = self.plantingevent_set.order_by('planting_id', 'date', 'pk')
        return list(self.packet_set.all()) + list(events)

    @property
    def plantings(self):
        """Return the plantings currently growing in this container.

        A planting is "in" the container when its most recent event that names
        a container (``planted_in``) points at this container.  This means a
        planting that was later transplanted elsewhere is no longer listed.
        """
        plantings = []
        for planting in Planting.objects.filter(deleted=False).select_related('packet__plant'):
            latest = planting.events.exclude(planted_in__isnull=True).order_by('-date', '-pk').first()
            if latest is not None and latest.planted_in_id == self.pk:
                plantings.append(planting)
        return plantings


class Plant(BarcodedBase):
    barcode_start = 0  # There won't actually be a 0, this just makes it match better with the others

    code = models.CharField(max_length=10, unique=True)  # Example: 'BR' or '豆DGD'
    deleted = models.BooleanField(default=False)
    name = models.CharField(max_length=100)  # Example: 'Dwarf bean, Gourmet Delight'
    spacing = models.CharField(max_length=10, null=True, blank=True)  # Example: '15' for sowing 15cm apart
    germination = models.CharField(
        max_length=10, null=True, blank=True
    )  # Example: '7' for germination in 7 days, or '10-14' for 10-14 days
    harvest = models.CharField(
        max_length=10, null=True, blank=True
    )  # Example: '60' for harvest in 60 days, or '60-70' for 60-70 days

    class Meta:
        # verbose_name_plural = "Plants"
        pass

    def __str__(self):
        return f'{self.barcode}: {self.name}'


class Packet(BarcodedBase):
    barcode_start = 100

    plant = models.ForeignKey(Plant, on_delete=models.PROTECT)
    container = models.ForeignKey(Container, on_delete=models.PROTECT, null=True, blank=True)
    deleted = models.BooleanField(default=False)
    # location = models.CharField(max_length=10, null=True, blank=True)  # Example: 'T=1062'
    brand = models.CharField(max_length=100, null=True, blank=True)  # Example: "Mr Fothergill's"
    expiry = models.CharField(null=True, blank=True)  # Example: 'Aug-20'
    full_name = models.CharField(max_length=100, null=True, blank=True)  # Example: 'Marketmore'
    notes = models.TextField(null=True, blank=True)  # Example: 'Sow in full sun'

    class Meta:
        # verbose_name_plural = "Packets"
        pass

    @property
    def plantings(self):
        """Return the plantings that use this packet."""
        return list(self.planting_set.all())

    @property
    def grouping_key(self):
        """Key used to group rows in a container's contents (see scan_contents)."""
        return ('packet', self.pk)

    def __str__(self):
        extra = f' ({self.full_name})' if self.full_name else ''
        return f'{self.barcode}: {self.plant.name}{extra}'


class Planting(BarcodedBase):
    barcode_start = 1000

    packet = models.ForeignKey(Packet, on_delete=models.PROTECT)
    deleted = models.BooleanField(default=False)
    germinated = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
        help_text=('Germination success, 0-3=nothing/some/most/all'),
    )

    class Meta:
        # verbose_name_plural = "Plantings"
        pass

    @property
    def first_event_date(self):
        """Date of the earliest event for this planting, or ``None``."""
        first = self.events.order_by('date', 'pk').first()
        return first.date if first else None

    def __str__(self):
        when = f' planted {first_event_date:%d-%b-%Y}' if (first_event_date := self.first_event_date) else ''
        return f'{self.barcode}: {self.packet.plant.name}{when}'


class PlantingEvent(models.Model):
    """A datestamped event about a planting.

    Events record what happened to a planting and when: it was planted, it was
    transplanted, or some other note-worthy occurrence.  The location details
    (``planted_in``, ``location``) and free-text ``notes`` live here rather than
    on the planting, so each event carries its own context.
    """

    class EventType(models.TextChoices):
        PLANTED = 'planted', 'Planted'
        GERMINATED = 'germinated', 'Germinated'
        TRANSPLANTED = 'transplanted', 'Transplanted'
        OTHER = 'other', 'Other'

    planting = models.ForeignKey(Planting, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    date = models.DateField()
    planted_in = models.ForeignKey(Container, on_delete=models.PROTECT, null=True, blank=True)
    location = models.CharField(max_length=100, null=True, blank=True)  # Example: 'Front garden parsley box'
    notes = models.TextField(null=True, blank=True)  # Example: "From Kath's seedling box"

    class Meta:
        ordering = ['date', 'pk']

    @property
    def verbose_name(self):
        """Human-readable model name (e.g. 'planting event').

        Mirrors ``BarcodedBase.verbose_name`` so the scan templates can
        distinguish a planting event from a packet in a container's contents.
        """
        return self._meta.verbose_name

    @property
    def grouping_key(self):
        """Key used to group rows in a container's contents (see scan_contents).

        Consecutive events for the same planting share a key, so the template
        can blank the repeated planting columns with ``{% ifchanged %}``.
        """
        return ('planting', self.planting_id)

    def __str__(self):
        return f'{self.get_event_type_display()} on {self.date}'


# Audit logging: record created/updated/deleted changes for the barcode-based
# models and for planting events.  The acting user is captured by
# ``auditlog.middleware.AuditlogMiddleware``.
auditlog.register(Container)
auditlog.register(Plant)
auditlog.register(Packet)
auditlog.register(Planting)
auditlog.register(PlantingEvent)
