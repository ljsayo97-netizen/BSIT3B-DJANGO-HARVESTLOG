"""User profile model extending Django's built-in User model.

Adds farming-related fields, user preferences, and profile completion tracking.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


GENDER_CHOICES = (
    ('M', 'Male'),
    ('F', 'Female'),
    ('O', 'Other'),
    ('P', 'Prefer not to say'),
)

EXPERIENCE_CHOICES = (
    ('NEW', 'New Farmer'),
    ('INTER', 'Intermediate'),
    ('EXP', 'Experienced'),
    ('EXP', 'Expert'),
)

FARM_SIZE_CHOICES = (
    ('SM', 'Small-scale (< 2 ha)'),
    ('MD', 'Medium (2-10 ha)'),
    ('LR', 'Large (10+ ha)'),
)


class UserProfile(models.Model):
    """Extended user profile for HarvestPH system."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='user',
    )

    # Contact & Location
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Phone Number',
        help_text='Optional. Primary contact number.',
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Address',
        help_text='Optional. Farm or home address.',
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='City',
        help_text='Optional.',
    )
    province = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Province/State',
        help_text='Optional.',
    )
    country = models.CharField(
        max_length=100,
        default='Philippines',
        verbose_name='Country',
    )

    # Farming Profile
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True,
        verbose_name='Gender',
        help_text='Optional.',
    )
    experience_level = models.CharField(
        max_length=6,
        choices=EXPERIENCE_CHOICES,
        default='NEW',
        verbose_name='Experience Level',
    )
    farm_size = models.CharField(
        max_length=2,
        choices=FARM_SIZE_CHOICES,
        blank=True,
        verbose_name='Farm Size',
        help_text='Optional. Your typical farm size.',
    )
    years_farming = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Years Farming',
        help_text='Optional. Number of years in farming.',
    )
    primary_crop = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Primary Crop',
        help_text='Optional. Your main crop or focus.',
    )

    # Preferences
    preferred_language = models.CharField(
        max_length=10,
        blank=True,
        default='en-ph',
        verbose_name='Preferred Language',
        help_text='Language code for interface (en-ph, en-us, etc.).',
    )
    preferred_timezone = models.CharField(
        max_length=50,
        blank=True,
        default='Asia/Manila',
        verbose_name='Preferred Timezone',
        help_text='Timezone identifier (Asia/Manila, UTC, etc.).',
    )
    theme_preference = models.CharField(
        max_length=20,
        blank=True,
        default='light',
        verbose_name='Theme Preference',
        help_text='light, dark, or auto.',
    )
    dashboard_layout = models.CharField(
        max_length=50,
        blank=True,
        default='default',
        verbose_name='Dashboard Layout',
        help_text='Layout preference for dashboard views.',
    )

    # Activity & Tracking
    last_activity = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Last Activity',
        help_text='When the user last performed an action in the system.',
    )
    total_logins = models.IntegerField(
        default=0,
        verbose_name='Total Logins',
        help_text='Count of all login sessions.',
    )
    last_login_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='Last Login IP',
    )

    # Profile Status
    is_profile_complete = models.BooleanField(
        default=False,
        verbose_name='Profile Complete',
        help_text='Automatically updated when key profile fields are filled.',
    )
    date_verified = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Email/Profile Verified',
    )

    # Metadata
    date_created = models.DateTimeField(auto_now_add=True, verbose_name='Date Created')
    date_updated = models.DateTimeField(auto_now=True, verbose_name='Date Updated')

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
        ordering = ['user__username']

    def __str__(self):
        return f'Profile: {self.user.username}'

    @property
    def full_name(self):
        """Return the user's full name."""
        return self.user.get_full_name() or self.user.username

    @property
    def display_name(self):
        """Return the display name (full name or username)."""
        name = self.user.get_full_name()
        return name if name else self.user.username

    def get_complete_name(self):
        """Return formatted name for display."""
        name = self.user.get_full_name()
        if name:
            return name
        if self.user.first_name:
            return self.user.first_name
        return self.user.username

    def update_last_activity(self):
        """Update the last activity timestamp."""
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])

    def increment_login_count(self):
        """Increment the total login counter."""
        self.total_logins = (self.total_logins or 0) + 1
        self.save(update_fields=['total_logins'])

    def mark_profile_complete(self):
        """Mark the profile as complete."""
        self.is_profile_complete = True
        self.date_verified = timezone.now()
        self.save(update_fields=['is_profile_complete', 'date_verified'])

    def is_online(self):
        """Check if the user was active recently (within 15 minutes)."""
        if self.last_activity:
            from datetime import timedelta
            now = timezone.now()
            return now - self.last_activity < timedelta(minutes=15)
        return False

    def get_experience_display(self):
        """Return the display name for experience level."""
        return dict(EXPERIENCE_CHOICES).get(self.experience_level, self.experience_level)

    def save(self, *args, **kwargs):
        """Override save to auto-update profile completeness."""
        # Check if profile is complete based on key fields
        has_name = bool(self.user.first_name or self.user.last_name)
        has_contact = bool(self.phone_number or self.address)
        has_farming = bool(self.experience_level and self.farm_size)

        if not self.is_profile_complete and (has_name or has_contact or has_farming):
            self.is_profile_complete = True

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Return URL to update this profile."""
        from django.urls import reverse
        return reverse('users:profile_update', kwargs={'pk': self.user.pk})


# Store choices for property access
UserProfile.EXPERIENCE_CHOICES_EXTERNAL = EXPERIENCE_CHOICES
UserProfile.FARM_SIZE_CHOICES_EXTERNAL = FARM_SIZE_CHOICES
UserProfile.GENDER_CHOICES_EXTERNAL = GENDER_CHOICES