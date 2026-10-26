"""Farm activity scheduling models."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class FarmActivity(models.Model):
    """A single agricultural activity scheduled at a location (e.g. irrigation)."""

    class ActivityType(models.TextChoices):
        CROP_INSPECTION = 'crop_inspection', 'Crop Inspection'
        IRRIGATION = 'irrigation', 'Irrigation'
        FERTILIZATION = 'fertilization', 'Fertilization'
        WEEDING = 'weeding', 'Weeding'
        PEST_INSPECTION = 'pest_inspection', 'Pest Inspection'
        DISEASE_INSPECTION = 'disease_inspection', 'Disease Inspection'
        HARVEST_PREPARATION = 'harvest_preparation', 'Harvest Preparation'
        EQUIPMENT_INSPECTION = 'equipment_inspection', 'Equipment Inspection'

    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'

    #: Allowed status movement: Pending -> In Progress -> Completed.
    STATUS_FLOW = {
        Status.PENDING: (Status.IN_PROGRESS,),
        Status.IN_PROGRESS: (Status.COMPLETED, Status.PENDING),
        Status.COMPLETED: (Status.IN_PROGRESS,),
    }

    STATUS_ACTIVE = (Status.PENDING, Status.IN_PROGRESS)

    ICONS = {
        ActivityType.CROP_INSPECTION: 'fas fa-eye',
        ActivityType.IRRIGATION: 'fas fa-tint',
        ActivityType.FERTILIZATION: 'fas fa-flask',
        ActivityType.WEEDING: 'fas fa-cut',
        ActivityType.PEST_INSPECTION: 'fas fa-bug',
        ActivityType.DISEASE_INSPECTION: 'fas fa-virus',
        ActivityType.HARVEST_PREPARATION: 'fas fa-clipboard-list',
        ActivityType.EQUIPMENT_INSPECTION: 'fas fa-tools',
    }

    PRIORITY_BADGES = {
        Priority.LOW: 'bg-secondary-lt text-secondary',
        Priority.MEDIUM: 'bg-info-lt text-info',
        Priority.HIGH: 'bg-warning-lt text-warning',
        Priority.URGENT: 'bg-danger-lt text-danger',
    }

    STATUS_BADGES = {
        Status.PENDING: 'bg-secondary-lt text-secondary',
        Status.IN_PROGRESS: 'bg-primary-lt text-primary',
        Status.COMPLETED: 'bg-success-lt text-success',
    }

    farm = models.ForeignKey(
        'farms.Farm',
        related_name='activities',
        on_delete=models.CASCADE,
        verbose_name='farm',
    )
    crop = models.ForeignKey(
        'crops.Crop',
        related_name='activities',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='crop',
    )
    activity_type = models.CharField(
        'activity type',
        max_length=40,
        choices=ActivityType.choices,
        help_text='Kind of agricultural work to be performed.',
    )
    location = models.CharField(
        'location',
        max_length=255,
        help_text='Location or area where the activity will take place (e.g. North Field, Block A).',
    )
    scheduled_date = models.DateField('scheduled date', default=timezone.localdate)
    assigned_worker = models.CharField(
        'assigned worker',
        max_length=255,
        help_text='Worker or team assigned to perform the activity.',
    )
    priority = models.CharField(
        'priority',
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    status = models.CharField(
        'status',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    remarks = models.TextField(
        'remarks',
        blank=True,
        help_text='Instructions, reminders, or observations for this activity.',
    )
    started_at = models.DateTimeField('started at', null=True, blank=True, editable=False)
    completed_at = models.DateTimeField('completed at', null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='activities',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'tblfarmactivities'
        ordering = ['scheduled_date', 'id']
        verbose_name = 'farm activity'
        verbose_name_plural = 'farm activities'

    def __str__(self):
        return f'{self.get_activity_type_display()} on {self.location} ({self.scheduled_date})'

    @property
    def icon(self):
        return self.ICONS.get(self.activity_type, 'fas fa-tasks')

    @property
    def priority_badge(self):
        return self.PRIORITY_BADGES.get(self.priority, 'bg-secondary-lt text-secondary')

    @property
    def status_badge(self):
        return self.STATUS_BADGES.get(self.status, 'bg-secondary-lt text-secondary')

    @property
    def is_active(self):
        return self.status in self.STATUS_ACTIVE

    @property
    def is_overdue(self):
        """An activity is overdue when its date passed but the work is unfinished."""
        return bool(
            self.scheduled_date
            and self.status != self.Status.COMPLETED
            and self.scheduled_date < timezone.localdate()
        )

    @property
    def days_until(self):
        if self.scheduled_date:
            return (self.scheduled_date - timezone.localdate()).days
        return None

    @property
    def due_today(self):
        return (
            self.status != self.Status.COMPLETED
            and self.scheduled_date == timezone.localdate()
        )

    @property
    def days_overdue(self):
        """Whole days the activity is past its scheduled date (0 when not overdue)."""
        days = self.days_until
        if days is None or days >= 0:
            return 0
        return abs(days)

    @property
    def next_status(self):
        """The next status following Pending -> In Progress -> Completed."""
        flow = {
            self.Status.PENDING: self.Status.IN_PROGRESS,
            self.Status.IN_PROGRESS: self.Status.COMPLETED,
            self.Status.COMPLETED: self.Status.IN_PROGRESS,
        }
        return flow.get(self.status)

    @property
    def next_status_label(self):
        labels = {
            (self.Status.PENDING, self.Status.IN_PROGRESS): 'Start Activity',
            (self.Status.IN_PROGRESS, self.Status.COMPLETED): 'Mark Completed',
            (self.Status.COMPLETED, self.Status.IN_PROGRESS): 'Reopen Activity',
        }
        return labels.get((self.status, self.next_status), 'Advance Status')

    def can_transition_to(self, new_status):
        """Whether moving to ``new_status`` follows the Pending -> ... flow."""
        if new_status == self.status:
            return True
        return new_status in self.STATUS_FLOW.get(self.status, ())

    def apply_status(self, new_status):
        """Move to ``new_status`` and keep the progress timestamps in sync."""
        if new_status == self.status:
            return

        if new_status == self.Status.IN_PROGRESS and self.started_at is None:
            self.started_at = timezone.now()
        if new_status == self.Status.PENDING:
            self.started_at = None
            self.completed_at = None
        if new_status == self.Status.COMPLETED:
            if self.started_at is None:
                self.started_at = timezone.now()
            self.completed_at = timezone.now()

        self.status = new_status
