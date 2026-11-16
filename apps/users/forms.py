"""Forms for user and profile management."""

from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileForm(forms.ModelForm):
    """Form for creating/updating UserProfile."""

    class Meta:
        model = UserProfile
        fields = (
            'phone_number',
            'address',
            'city',
            'province',
            'country',
            'gender',
            'experience_level',
            'farm_size',
            'years_farming',
            'primary_crop',
            'preferred_language',
            'preferred_timezone',
            'theme_preference',
            'dashboard_layout',
            'last_activity',
            'total_logins',
            'last_login_ip',
            'is_profile_complete',
            'date_verified',
        )
        widgets = {
            'phone_number': forms.TextInput(attrs={'placeholder': '+639171234567'}),
            'address': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Street, Barangay, City'}),
            'city': forms.TextInput(attrs={'placeholder': 'City'}),
            'province': forms.TextInput(attrs={'placeholder': 'Province/State'}),
            'primary_crop': forms.TextInput(attrs={'placeholder': 'e.g., Rice, Corn, Vegetables'}),
            'experience_level': forms.Select(attrs={'class': 'select2'}),
            'farm_size': forms.Select(attrs={'class': 'select2'}),
            'theme_preference': forms.Select(choices=[
                ('light', 'Light'),
                ('dark', 'Dark'),
                ('auto', 'Auto (System)'),
            ]),
            'dashboard_layout': forms.TextInput(attrs={'placeholder': 'e.g., default, compact, detailed'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make fields optional except where needed
        self.fields['user'].widget = forms.HiddenInput()
        self.fields['last_activity'].widget = forms.HiddenInput()
        self.fields['total_logins'].widget = forms.HiddenInput()
        self.fields['is_profile_complete'].widget = forms.HiddenInput()
        self.fields['date_verified'].widget = forms.HiddenInput()


class UserCreationFormWithProfile(UserCreationForm):
    """Custom user creation form that also creates a profile."""

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')

    def save(self, commit=True):
        """Save the user and create a profile."""
        user = super().save(commit=commit)
        if commit:
            # Create the profile
            from .models import UserProfile
            UserProfile.objects.get_or_create(user=user)
        return user


class UserChangeFormWithProfile(UserChangeForm):
    """Custom user change form that also handles profile."""

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff', 'is_superuser')

    def save(self, commit=True):
        """Save the user."""
        user = super().save(commit=commit)
        return user