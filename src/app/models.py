import re

from auditlog.registry import auditlog
from django.core.exceptions import ValidationError
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

        return reverse('app:scan', query={'barcode': self.barcode})

    def get_absolute_url(self):
        """Return the canonical public URL for this object."""
        return self.scan_url

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

    class Meta:
        # Newest first, so container dropdowns list the most recent containers
        # at the top.
        ordering = ['-pk']

    def __str__(self):
        return f'{self.barcode}: {self.name}'

    @property
    def contents(self):
        """Return the packets and planting events stored in this container.

        A planting's events are listed in the container the planting is
        currently in: the container named by its most recent located event (see
        ``plantings``).  A planting whose latest located event gives only a
        free-text ``location`` is in no container, so it is not listed
        anywhere.  All of the planting's events are shown (grouped by planting,
        ordered by date), so its planted, germinated and transplanted events
        appear together.
        """
        events = PlantingEvent.objects.filter(planting__in=self.plantings).order_by('planting_id', 'date', 'pk')
        return list(self.packet_set.all()) + list(events)

    @property
    def plantings(self):
        """Return the plantings currently growing in this container.

        ``planted_in`` and ``location`` are the two halves of a single
        location, so a planting's location is whatever its most recent located
        event (``Planting.location_event``) records.  The planting is "in" this
        container only when that event's ``planted_in`` points here: a
        transplant into another container moves it, and a transplant to a
        free-text ``location`` leaves it in no container at all, in both cases
        removing it from this container's list.
        """
        plantings = []
        for planting in Planting.objects.filter(deleted=False).select_related('packet__plant'):
            latest = planting.location_event
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

    @property
    def planted_date(self):
        """Date of the earliest ``planted`` event, or ``None``."""
        first = self.events.filter(event_type=PlantingEvent.EventType.PLANTED).order_by('date', 'pk').first()
        return first.date if first else None

    @property
    def latest_event(self):
        """Most recent event for this planting, or ``None``.

        Ties on ``date`` are broken the same way as in
        ``Container.plantings``, so a transplant outranks a germination on the
        same day.
        """
        return self.events.annotate(recency=PLANTING_EVENT_RECENCY).order_by('-date', '-recency', '-pk').first()

    @property
    def location_event(self):
        """Most recent event that has a location, or ``None``.

        ``germinated`` events carry no location details (see
        ``PlantingEvent.clean``), so they are skipped: a planting's location is
        whatever its latest ``planted`` or ``transplanted`` event recorded.
        """
        return (
            self.events.filter(PlantingEvent.location_q())
            .annotate(recency=PLANTING_EVENT_RECENCY)
            .order_by('-date', '-recency', '-pk')
            .first()
        )

    @property
    def location(self):
        """Free-text location on the planting's most recent located event, if any.

        This is only the ``location`` half of the location; the other half is the
        container in ``location_event.planted_in``.
        """
        event = self.location_event
        return event.location if event is not None else None

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
        constraints = [
            # A planting is planted once; later moves are transplant events.
            models.UniqueConstraint(
                fields=['planting'],
                condition=models.Q(event_type='planted'),
                name='unique_planted_event_per_planting',
            ),
        ]

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

    @staticmethod
    def location_q():
        """``Q`` matching events that specify a location.

        ``planted_in`` and ``location`` are two parts of one location, so an
        event has a location when either is set.  An empty string is treated as
        unset, so a form submitted with a blank ``location`` is not a location.
        """
        return models.Q(planted_in__isnull=False) | (models.Q(location__isnull=False) & ~models.Q(location=''))

    @property
    def has_location(self):
        """Whether this event specifies a location (a container, text, or both)."""
        return self.planted_in_id is not None or bool(self.location)

    def clean(self):
        """Reject invalid event combinations.

        Location details belong to the ``planted`` and ``transplanted`` events;
        a ``germinated`` event records only when germination was seen.  Storing
        the same container or location on it would duplicate the preceding
        event's data and let the two copies drift apart.

        A planting is planted once (see the ``unique_planted_event_per_planting``
        constraint); later moves are ``transplanted`` events.
        """
        super().clean()
        if self.event_type == self.EventType.GERMINATED and self.has_location:
            raise ValidationError({'planted_in': 'A germinated event cannot have a container or location set.'})
        if (
            self.event_type == self.EventType.PLANTED
            and self.pk is None
            and self.planting_id is not None
            and PlantingEvent.objects.filter(planting_id=self.planting_id, event_type=self.EventType.PLANTED).exists()
        ):
            raise ValidationError({'event_type': 'This planting already has a planted event.'})

    def save(self, *args, **kwargs):
        """Validate the event before writing it, so a bad row cannot be saved."""
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_event_type_display()} on {self.date}'


# Priority used to break ties between events that share a date: a transplant is
# treated as more recent than germination, which in turn outranks a planting.
# This means a transplant on the same day as a germination moves the planting to
# its new container rather than leaving it in the germination container.
PLANTING_EVENT_RECENCY = models.Case(
    models.When(event_type=PlantingEvent.EventType.TRANSPLANTED, then=models.Value(2)),
    models.When(event_type=PlantingEvent.EventType.GERMINATED, then=models.Value(1)),
    default=models.Value(0),
    output_field=models.IntegerField(),
)


# Audit logging: record created/updated/deleted changes for the barcode-based
# models and for planting events.  The acting user is captured by
# ``auditlog.middleware.AuditlogMiddleware``.
auditlog.register(Container)
auditlog.register(Plant)
auditlog.register(Packet)
auditlog.register(Planting)
auditlog.register(PlantingEvent)
