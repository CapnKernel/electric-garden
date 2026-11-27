import re
from datetime import date, timedelta

from auditlog.registry import auditlog
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .placement import Placement


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
    """Base for objects that have a barcode, a URL and a scan history.

    A concrete subclass sets:

    * ``barcode_start``: the first id in its barcode range, which also gives the
      zero-padded width unless ``barcode_width`` says otherwise;
    * ``prefix``: ``P=`` for plants, packets and plantings, ``PC=`` for
      containers;
    * ``detail_url_name``: the URL pattern of its detail page;
    * ``detail_template``: the partial that renders one object of this model.
    """

    # --- Barcoding ---
    barcode_start = 0
    prefix = 'P='
    # Number of digits the id is zero-padded to in the barcode.  Derived from
    # ``barcode_start`` (e.g. 100 -> 3 digits, 1000 -> 4 digits) unless set
    # explicitly on the subclass.
    barcode_width = None

    objects = BarcodeManager()

    class Meta:
        abstract = True

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

    @classmethod
    def pk_from_barcode(cls, barcode):
        """Return the primary key encoded in ``barcode`` for this model.

        Matching is case-insensitive, so ``pc=7`` and ``PC=7`` are the same
        barcode.
        """
        return int((barcode or '').upper().removeprefix(cls.prefix.upper()))

    @classmethod
    def from_barcode(cls, barcode):
        """Return the instance matching ``barcode``, or ``None`` if not found.

        The barcode must be of the form ``<prefix><integer>`` for this model.
        Matching is case-insensitive, so ``pc=7`` and ``PC=7`` are the same
        barcode.
        """
        match = re.match(f'^{re.escape(cls.prefix.upper())}(\\d+)$', (barcode or '').upper())
        if not match:
            return None
        return cls.objects.filter(pk=match.group(1)).first()

    # --- Scanning ---
    last_scanned_at = models.DateTimeField(null=True, blank=True, help_text='When this object was last scanned')

    def mark_scanned(self):
        """Record that this object was just scanned."""
        self.last_scanned_at = timezone.now()
        self.save(update_fields=['last_scanned_at'])

    @property
    def scan_redirect_url(self):
        """URL that marks this object scanned and then shows its detail page."""
        return reverse('app:scan', query={'q': self.barcode})

    # --- URLs ---
    # Name of the URL pattern for this model's detail page, used by
    # ``get_absolute_url``; set on each concrete subclass.
    detail_url_name = None
    # Partial that renders one object of this model, e.g. on its detail page.
    detail_template = None

    @property
    def detail_url(self):
        """URL of this object's detail page (the canonical public URL)."""
        return reverse(f'app:{self.detail_url_name}', kwargs={'pk': self.pk})

    def get_absolute_url(self):
        """Return the canonical public URL for this object."""
        return self.detail_url

    @property
    def admin_url(self):
        """URL of this object's admin change page."""

        meta = self._meta
        return reverse(f'admin:{meta.app_label}_{meta.model_name}_change', args=[self.pk])

    # --- Display ---
    @property
    def model_label(self):
        """Human-readable model name (e.g. 'plant', 'container')."""
        return self._meta.verbose_name

    @property
    def label(self):
        """Short human-readable name shown after the barcode (e.g. in breadcrumbs)."""
        return ''


class Container(BarcodedBase):
    barcode_start = 1
    prefix = 'PC='
    detail_url_name = 'container_detail'
    detail_template = 'app/partials/detail/container.html'

    name = models.CharField(max_length=100)  # Example: 'Blue ribbon 1'

    class Meta:
        # Newest first, so container dropdowns list the most recent containers
        # at the top.
        ordering = ('-pk',)

    @property
    def label(self):
        """The container's name, e.g. 'Blue ribbon 1'."""
        return self.name

    def __str__(self):
        return f'{self.barcode}: {self.name}'

    @property
    def packets(self):
        """The packets stored in this container."""
        return self.packet_set.all()

    @property
    def plantings(self):
        """The plantings currently growing in this container.

        ``planted_in`` and ``location`` are the two halves of a single
        location, so a planting's location is whatever its most recent located
        event (``Planting.location_event``) records.  The planting is "in" this
        container only when that event's ``planted_in`` points here: a
        transplant into another container moves it, and a transplant to a
        free-text ``location`` leaves it in no container at all.

        See ``PlantingManager.in_container`` for the query.
        """
        return Planting.objects.in_container(self)

    @property
    def planting_events(self):
        """Every event of every planting currently in this container.

        Ordered by planting and then date, so the container view can show one
        row per planting listing its planted, germinated and transplanted events
        together.
        """
        return (
            PlantingEvent.objects.filter(planting__in=self.plantings)
            .select_related('planting__packet__plant', 'planted_in')
            .order_by('planting_id', 'date', 'pk')
        )


class Plant(BarcodedBase):
    barcode_start = 0  # There won't actually be a 0, this just makes it match better with the others
    detail_url_name = 'plant_detail'
    detail_template = 'app/partials/detail/plant.html'

    code = models.CharField(max_length=10, unique=True)  # Example: 'BR' or '豆DGD'
    deleted = models.BooleanField(default=False)
    name = models.CharField(max_length=100)  # Example: 'Dwarf bean, Gourmet Delight'
    spacing = models.CharField(max_length=10, null=True, blank=True)  # Example: '15' for planting 15cm apart
    germination = models.CharField(
        max_length=10, null=True, blank=True
    )  # Example: '7' for germination in 7 days, or '10-14' for 10-14 days
    harvest = models.CharField(
        max_length=10, null=True, blank=True
    )  # Example: '60' for harvest in 60 days, or '60-70' for 60-70 days

    class Meta:
        # verbose_name_plural = "Plants"
        pass

    @property
    def label(self):
        """The plant's name, e.g. 'Dwarf bean, Gourmet Delight'."""
        return self.name

    def __str__(self):
        return f'{self.barcode}: {self.name}'

    @property
    def packets(self):
        """Return the plant's active packets, each with a count of its plantings."""
        return self.packet_set.filter(deleted=False).annotate(planting_count=models.Count('planting')).order_by('pk')

    @property
    def plant_weeks_str(self):
        """The plant's active planting schedules, as 'week 44-8' style labels."""
        return ', '.join(schedule.label for schedule in self.planting_schedules.filter(active=True)) or '-'

    @property
    def plant_months_str(self):
        """The plant's active planting schedules in approximate months, e.g. 'Sep, week 4ish - Oct, week 4ish'."""
        return ', '.join(schedule.month_hint for schedule in self.planting_schedules.filter(active=True)) or '-'

    def plantable_in(self, week):
        """Whether this plant has any active planting schedule that includes ISO ``week``."""
        return PlantingSchedule.for_week(week).filter(plant=self).exists()

    def last_planted_date(self):
        """Date of the most recent ``planted`` event for any of this plant's plantings, or ``None``."""
        return (
            PlantingEvent.objects.filter(planting__packet__plant=self, event_type=PlantingEvent.EventType.PLANTED)
            .order_by('-date')
            .values_list('date', flat=True)
            .first()
        )

    def next_plant_date(self, day=None):
        """Next succession planting date for the schedule covering ``day``, or ``None``.

        Returns the Monday of the current ISO week when the plant has never been
        planted, and the last planted date plus the schedule's interval otherwise.
        Returns ``None`` unless an active schedule covering ``day`` declares an
        interval.
        """
        day = day or timezone.localdate()
        week = day.isocalendar().week
        schedule = PlantingSchedule.for_week(week).filter(plant=self).order_by('start_week').first()
        if schedule is None or not schedule.repeat_every_weeks:
            return None
        last = self.last_planted_date()
        if last is None:
            return date.fromisocalendar(day.year, week, 1)
        due = last + timedelta(weeks=schedule.repeat_every_weeks)
        return max(due, day)


class PlantingSchedule(models.Model):
    """A range of ISO weeks during which a plant can be planted.

    ``start_week`` and ``end_week`` are ISO week numbers (1-53); both ends are
    inclusive.  A schedule whose ``start_week`` is greater than its ``end_week``
    wraps the end of the year, so ``44``-``8`` means "from week 44 until week
    8".  The schedule repeats every year.

    ``repeat_every_weeks`` marks the schedule as a succession planting: the crop
    is re-planted at that interval, starting in the schedule's first week.  It is a
    hint for the dashboard; matching by week ignores it.

    ``active`` can be set to ``False`` so a schedule can be constructed ahead
    of time, and switched on once it is ready to be acted on.
    Inactive schedules never appear in plant-now queries.

    ``priority`` orders schedules (higher first); ties are broken by plant and
    start week.
    """

    class Status(models.TextChoices):
        DUE = 'due', 'Plant now'
        PLANTED = 'planted', 'Already planted'
        OVERDUE = 'overdue', 'Overdue'

    plant = models.ForeignKey(Plant, on_delete=models.CASCADE, related_name='planting_schedules')
    start_week = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(53)])
    end_week = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(53)])
    repeat_every_weeks = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(52)],
        help_text='Succession planting: re-plant every this many weeks. Blank to plant once.',
    )
    notes = models.CharField(max_length=100, blank=True)  # Example: 'after last frost'
    active = models.BooleanField(
        default=True,
        help_text='Switch off to hide from plant-now.',
    )
    priority = models.FloatField(default=0)  # Higher sorts first; ties break on plant then start week

    class Meta:
        ordering = ('-priority', 'plant_id', 'start_week')
        constraints = (
            models.UniqueConstraint(fields=('plant', 'start_week', 'end_week'), name='unique_planting_schedule'),
        )
        indexes = (models.Index(fields=('start_week', 'end_week')),)

    @classmethod
    def week_q(cls, week):
        """``Q`` matching schedules whose window includes ISO ``week``.

        A window that does not wrap contains ``week`` when ``start <= week <=
        end``.  A window that wraps (``start > end``) can never satisfy that, so
        it matches when ``week >= start`` or ``week <= end``.
        """
        unwrapped = models.Q(start_week__lte=week, end_week__gte=week)
        wrapped = models.Q(
            models.Q(start_week__lte=week) | models.Q(end_week__gte=week),
            start_week__gt=models.F('end_week'),
        )
        return unwrapped | wrapped

    @classmethod
    def for_week(cls, week):
        """Active windows that include ISO ``week``."""
        return cls.objects.filter(cls.week_q(week), active=True)

    @classmethod
    def for_date(cls, day=None):
        """Active windows that include the ISO week containing ``day`` (default: today, local time)."""
        week = (day or timezone.localdate()).isocalendar().week
        return cls.for_week(week)

    def includes_week(self, week):
        """Whether this schedule's window includes ISO ``week``."""
        if self.start_week <= self.end_week:
            return self.start_week <= week <= self.end_week
        return week >= self.start_week or week <= self.end_week

    # An ISO week number only maps to a date in a year that has that week, so
    # labels are derived from a 53-week year (2026, 2032, ...).  The month is
    # approximate: a week can straddle a month boundary, hence the "ish".
    REFERENCE_YEAR = 2026

    @classmethod
    def week_label(cls, week):
        """Approximate calendar position of ISO ``week``, e.g. 'Feb, week 2ish'."""
        monday = date.fromisocalendar(cls.REFERENCE_YEAR, week, 1)
        return f'{monday:%b}, week {(monday.day - 1) // 7 + 1}ish'

    @staticmethod
    def monday_of(year, week):
        """Monday of ISO ``week`` in ``year``, clamped to that year's last week."""
        last_week = date(year, 12, 28).isocalendar().week
        return date.fromisocalendar(year, min(week, last_week), 1)

    def cycle_start_date(self, day):
        """Monday of ``start_week`` for the window cycle that contains ``day``.

        A wrapping window that has not yet reached ``start_week`` this year began
        in the previous ISO year, so its cycle start is there.
        """
        iso = day.isocalendar()
        year = iso.year if self.start_week <= iso.week else iso.year - 1
        return self.monday_of(year, self.start_week)

    def due_date(self, day):
        """Date the current cycle's planting is, or was, due.

        Succession schedules fall due ``repeat_every_weeks`` after the last
        planting; one-off schedules are due from the start of the window cycle.
        This is the single definition of "due": ``plant_status`` and the
        dashboard both use it.
        """
        last = self.plant.last_planted_date()
        if self.repeat_every_weeks and last is not None:
            return last + timedelta(weeks=self.repeat_every_weeks)
        return self.cycle_start_date(day)

    def plant_due_date(self, day):
        """The due date, under the name callers and the dashboard already use."""
        return self.due_date(day)

    def plant_status(self, day=None):
        """Classify the schedule for ``day`` as due, already planted, or overdue.

        A succession schedule falls due ``repeat_every_weeks`` after its last
        planting: before that it is already planted, during that ISO week it is due,
        and after it it is overdue.  A one-off schedule is due anywhere in its
        window and only counts as planted once a planting falls inside the current
        window cycle.
        """
        day = day or timezone.localdate()
        last = self.plant.last_planted_date()
        monday = self.monday_of(day.isocalendar().year, day.isocalendar().week)
        if self.repeat_every_weeks and last is not None:
            due = self.due_date(day)
            if due > day:
                return self.Status.PLANTED
            if due >= monday:
                return self.Status.DUE
            return self.Status.OVERDUE
        if last is not None and last >= self.cycle_start_date(day):
            return self.Status.PLANTED
        return self.Status.DUE

    @classmethod
    def dashboard_counts(cls, day=None):
        """Count schedules for the dashboard, keyed by status plus ``inactive``.

        Active schedules whose window includes the ISO week of ``day`` are
        classified with ``plant_status``.  Everything else -- inactive schedules,
        windows outside the current week, and schedules for deleted plants -- is
        counted under ``inactive``, because none of them can be planted now.
        """
        day = day or timezone.localdate()
        week = day.isocalendar().week
        counts = {status.value: 0 for status in cls.Status}
        counts['inactive'] = 0
        counts['total'] = 0
        for schedule in cls.objects.filter(plant__deleted=False).select_related('plant'):
            counts['total'] += 1
            if not schedule.active or not schedule.includes_week(week):
                counts['inactive'] += 1
            else:
                counts[schedule.plant_status(day).value] += 1
        return counts

    def span_weeks(self):
        """Number of ISO weeks the window covers, counting the wrapped year end.

        Weeks are normalised to a 53-week ISO year, so the count does not depend
        on the length of the year the schedule is read in; a wrapping window such
        as 44-8 therefore always spans 18 weeks.
        """
        return (self.end_week - self.start_week) % 53 + 1

    def succession_weeks(self):
        """ISO weeks at which the crop is planted, honouring ``repeat_every_weeks``.

        Without an interval this is every week in the window, because the crop
        may be planted at any point in it.
        """
        interval = self.repeat_every_weeks or 1
        return [((self.start_week - 1 + offset) % 53) + 1 for offset in range(0, self.span_weeks(), interval)]

    @property
    def label(self):
        """Human-readable week range, e.g. 'week 44-8 every 3 weeks'."""
        if self.start_week == self.end_week:
            label = f'week {self.start_week}'
        else:
            label = f'week {self.start_week}-{self.end_week}'
        if self.repeat_every_weeks:
            label += f' every {self.repeat_every_weeks} weeks'
        return label

    @property
    def month_hint(self):
        """Approximate month range for the window, e.g. 'Sep, week 4ish - Oct, week 4ish'."""
        if self.start_week == self.end_week:
            return self.week_label(self.start_week)
        return f'{self.week_label(self.start_week)} - {self.week_label(self.end_week)}'

    def __str__(self):
        return f'{self.plant.name}: {self.label}'


class Packet(BarcodedBase):
    barcode_start = 100
    detail_url_name = 'packet_detail'
    detail_template = 'app/partials/detail/packet.html'

    plant = models.ForeignKey(Plant, on_delete=models.PROTECT)
    container = models.ForeignKey(Container, on_delete=models.PROTECT, null=True, blank=True)
    deleted = models.BooleanField(default=False)
    # location = models.CharField(max_length=10, null=True, blank=True)  # Example: 'T=1062'
    brand = models.CharField(max_length=100, null=True, blank=True)  # Example: "Mr Fothergill's"
    expiry = models.CharField(null=True, blank=True)  # Example: 'Aug-20'
    full_name = models.CharField(max_length=100, null=True, blank=True)  # Example: 'Marketmore'
    notes = models.TextField(null=True, blank=True)  # Example: 'Plant in full sun'

    class Meta:
        # verbose_name_plural = "Packets"
        pass

    @property
    def plantings(self):
        """Return the plantings that use this packet."""
        return list(self.planting_set.all())

    @property
    def placement(self):
        """Where this packet is kept: its container, with no free-text detail."""
        return Placement(container=self.container)

    @property
    def label(self):
        """The packet's plant name, plus its variety (``full_name``) if set."""
        if self.full_name:
            return f'{self.plant.name} ({self.full_name})'
        return self.plant.name

    def __str__(self):
        return f'{self.barcode}: {self.label}'


class PlantingManager(BarcodeManager):
    """Manager for plantings, adding container membership lookup."""

    def in_container(self, container):
        """Plantings whose latest located event names ``container``.

        A location is one ``Placement``, so the latest event with any placement
        decides where a planting is: a later event naming another container
        moves it, and one that gives only free text leaves it in no container at
        all.
        """
        latest_placed_event = (
            PlantingEvent.objects.filter(planting=models.OuterRef('pk'))
            .filter(PlantingEvent.has_placement_q())
            .annotate(recency=PLANTING_EVENT_RECENCY)
            .order_by('-date', '-recency', '-pk')
        )
        return (
            self.filter(deleted=False)
            .annotate(placement_container=models.Subquery(latest_placed_event.values('planted_in_id')[:1]))
            .filter(placement_container=container.pk)
            .select_related('packet__plant')
        )


class Planting(BarcodedBase):
    barcode_start = 1000
    detail_url_name = 'planting_detail'
    detail_template = 'app/partials/detail/planting.html'

    objects = PlantingManager()

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
    def planted_date(self):
        """Date of the planting's ``planted`` event, or ``None``.

        A planting is planted once (see the ``unique_planted_event_per_planting``
        constraint), so this is the whole of "when it was planted".
        """
        planted = self.events.filter(event_type=PlantingEvent.EventType.PLANTED).first()
        return planted.date if planted else None

    @property
    def location_event(self):
        """Most recent event that records a placement, or ``None``.

        The raw event behind ``placement``: ``germinated`` events carry no
        placement (see ``PlantingEvent.clean``), so they are skipped, and a
        planting's location is whatever its latest ``planted`` or
        ``transplanted`` event recorded.  Ties on ``date`` are broken so a
        transplant outranks a germination outranks a planting.
        """
        return (
            self.events.filter(PlantingEvent.has_placement_q())
            .select_related('planted_in')
            .annotate(recency=PLANTING_EVENT_RECENCY)
            .order_by('-date', '-recency', '-pk')
            .first()
        )

    @property
    def placement(self):
        """Where this planting is: the placement on its most recent located event."""
        return Placement.from_event(self.location_event)

    def is_in(self, container):
        """Whether this planting is currently in ``container``."""
        return self.placement.is_in(container)

    def set_germination(self, score, day=None):
        """Record a germination outcome, keeping the score and its event in step.

        ``score`` is 0-3, or ``None`` for "nothing germinated".  A score sets the
        field and creates the planting's ``germinated`` event, or redates it;
        ``None`` clears the field and deletes the event.  A germinated event
        records only when germination was seen, so it carries no placement (see
        ``PlantingEvent.clean``).

        Returns whether anything changed.  A change marks the planting scanned,
        so the field and the event can never drift apart.
        """
        day = day or timezone.localdate()
        event = self.events.filter(event_type=PlantingEvent.EventType.GERMINATED).order_by('-date', '-pk').first()
        changed = self.germinated != score

        if score is None:
            if event is not None:
                event.delete()
                changed = True
        elif event is None:
            PlantingEvent.objects.create(planting=self, event_type=PlantingEvent.EventType.GERMINATED, date=day)
            changed = True
        elif event.date != day:
            event.date = day
            event.save(update_fields=['date'])
            changed = True

        if self.germinated != score:
            self.germinated = score
            self.save(update_fields=['germinated'])
        if changed:
            self.mark_scanned()
        return changed

    @property
    def label(self):
        """The planted variety's name."""
        return self.packet.plant.name

    def __str__(self):
        """Barcode, plant name and planting date, e.g. ``P=1001: Dwarf bean planted 01-Jan-2026``.

        The date comes from ``planted_date``, so this costs one query; callers
        that render many plantings should use a queryset annotation instead.
        """
        when = f' planted {planted:%d-%b-%Y}' if (planted := self.planted_date) else ''
        return f'{self.barcode}: {self.label}{when}'


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
        ordering = ('date', 'pk')
        constraints = (
            # A planting is planted once; later moves are transplant events.
            models.UniqueConstraint(
                fields=['planting'],
                condition=models.Q(event_type='planted'),
                name='unique_planted_event_per_planting',
            ),
        )

    @staticmethod
    def has_placement_q():
        """``Q`` matching events that record a placement.

        ``planted_in`` and ``location`` are the two halves of one placement, so
        an event has one when either is set.  An empty string counts as unset,
        so a form submitted with a blank ``location`` records no placement.
        """
        return models.Q(planted_in__isnull=False) | (models.Q(location__isnull=False) & ~models.Q(location=''))

    @classmethod
    def last_placement(cls):
        """The most recently recorded placement, or ``EMPTY``.

        Offered as a starting point when recording a new planting.  Both halves
        come from the same event, so the container and the free text offered are
        the pair that was used together.
        """
        event = cls.objects.filter(cls.has_placement_q()).select_related('planted_in').order_by('-date', '-pk').first()
        return Placement.from_event(event)

    @property
    def placement(self):
        """Where this event happened: the container and free text together."""
        return Placement(container=self.planted_in, text=self.location)

    def set_placement(self, placement):
        """Set both halves of this event's location from one ``Placement``."""
        self.planted_in = placement.container
        self.location = placement.text

    @property
    def has_location(self):
        """Whether this event records a placement.

        The id-based form of ``not placement.is_empty``, so validation does not
        load the container when the instance only carries ``planted_in_id``.
        """
        return self.planted_in_id is not None or bool(self.location)

    def clean(self):
        """Reject invalid event combinations.

        The first event created for a particular planting must be a PLANTED event,
        and a planting may only have one PLANTED event (see the
        ``unique_planted_event_per_planting`` constraint).  Other event types can be
        created after the PLANTED event.

        The PLANTED event must be the earliest event: no event may be dated before
        it, and it may not be dated after an event that already exists.  The other
        event types therefore follow the PLANTED event in both creation order and
        date.

        Location details belong to the ``planted`` and ``transplanted`` events;
        a ``germinated`` event records only when germination was seen, so it's an
        error to set location on a germination event.

        An event with no planting set (a blank admin inline row) is not checked.
        """
        super().clean()
        if self.event_type == self.EventType.GERMINATED and self.has_location:
            raise ValidationError({'planted_in': 'A germinated event cannot have a container or location set.'})
        if self.planting_id is None:
            return

        # ``date`` may still be a string when the instance has not been saved, so
        # compare the converted value; ``others`` always holds dates from the db.
        event_date = self._meta.get_field('date').to_python(self.date)
        others = PlantingEvent.objects.filter(planting_id=self.planting_id).exclude(pk=self.pk)
        planted = others.filter(event_type=self.EventType.PLANTED).order_by('date', 'pk').first()
        if self.event_type == self.EventType.PLANTED:
            if planted is not None:
                raise ValidationError({'event_type': 'This planting already has a planted event.'})
            if self.pk is None and others.exists():
                raise ValidationError({'event_type': 'Record the planted event before any other event.'})
            if others.filter(date__lt=event_date).exists():
                raise ValidationError({'date': 'The planted event must be the earliest event.'})
        elif planted is None:
            raise ValidationError({'event_type': 'Record the planted event before any other event.'})
        elif event_date < planted.date:
            raise ValidationError({'date': 'An event cannot be dated before the planted event.'})

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
