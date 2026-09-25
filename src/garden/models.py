from django.db import models
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

    objects = BarcodeManager()

    class Meta:
        abstract = True

    @property
    def barcode(self):
        return f'{self.prefix}{self.id}'

    @classmethod
    def pk_from_barcode(cls, barcode):
        """Return the primary key encoded in ``barcode`` for this model."""
        return int(barcode.removeprefix(cls.prefix))


class Container(BarcodedBase):
    barcode_start = 1
    prefix = 'PC='

    name = models.CharField(max_length=100)  # Example: 'Blue ribbon 1'

    def __str__(self):
        return self.name


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
        return self.name


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

    def __str__(self):
        return f'{self.barcode}: {self.plant.name}'


class Planting(BarcodedBase):
    barcode_start = 1000

    packet = models.ForeignKey(Packet, on_delete=models.PROTECT)
    deleted = models.BooleanField(default=False)
    planted = models.DateField()
    location = models.CharField(max_length=100, null=True, blank=True)  # Example: 'Front garden parsley box'
    notes = models.TextField(null=True, blank=True)  # Example: "From Kath's seedling box"

    class Meta:
        # verbose_name_plural = "Plantings"
        pass

    def __str__(self):
        return f'{self.barcode}: {self.packet.plant.name} on {self.planted}'


class SheetChangeLog(models.Model):
    """Audit log of every change received from Google Sheets.

    Each row is one webhook delivery from the Apps Script ``onEdit`` trigger.
    Rows start as ``pending`` and are later moved to ``applied``, ``conflict``
    or ``error`` as they are reconciled against the Django models.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPLIED = 'applied', 'Applied'
        CONFLICT = 'conflict', 'Conflict'
        ERROR = 'error', 'Error'

    sheet_name = models.CharField(max_length=255)
    range = models.CharField(max_length=255)
    key = models.CharField(max_length=255, null=True, blank=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    edit_timestamp = models.DateTimeField(null=True, blank=True)
    user_email = models.EmailField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    applied_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        'authuser.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_sheet_changes',
    )
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['status', '-received_at']),
        ]

    def __str__(self):
        return f'{self.sheet_name}!{self.range} ({self.status})'
