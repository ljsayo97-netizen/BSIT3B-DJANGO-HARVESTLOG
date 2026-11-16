"""Admin configuration for user models and profiles."""

from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import UserProfile
from .forms import UserProfileForm


# Unregister the default User admin if already registered
try:
    admin.site.unregister(User)
except admin.site.NotRegistered:
    pass


class UserProfileInline(admin.StackedInline):
    """Inline profile editing on the user admin page."""
    model = UserProfile
    form = UserProfileForm
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin interface for UserProfile model."""

    list_display = (
        'user',
        'experience_level',
        'farm_size',
        'city',
        'is_profile_complete',
        'total_logins',
        'date_created',
    )
    list_filter = (
        'experience_level',
        'farm_size',
        'is_profile_complete',
        'date_created',
    )
    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name',
        'user__email',
        'phone_number',
        'city',
    )
    raw_id_fields = ('user',)
    date_hierarchy = 'date_created'

    fieldsets = (
        (None, {'fields': ('user',)}),
        ('Contact Information', {
            'fields': ('phone_number', 'address', 'city', 'province', 'country')
        }),
        ('Farming Profile', {
            'fields': ('experience_level', 'farm_size', 'years_farming', 'primary_crop'),
            'classes': ('collapse',),
        }),
        ('Preferences', {
            'fields': ('preferred_language', 'preferred_timezone', 'theme_preference', 'dashboard_layout'),
            'classes': ('collapse',),
        }),
        ('Activity', {
            'fields': ('last_activity', 'total_logins', 'last_login_ip'),
            'classes': ('collapse',),
        }),
        ('Status', {
            'fields': ('is_profile_complete', 'date_verified'),
        }),
    )

    def user_full_name(self, obj):
        """Display user's full name in admin list."""
        return obj.user.get_full_name() or obj.user.username
    user_full_name.short_description = 'User'

    def is_profile_complete_display(self, obj):
        """Show profile completion status with color."""
        if obj.is_profile_complete:
            return '✓ Complete'
        return '✗ Incomplete'
    is_profile_complete_display.short_description = 'Complete'


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    """Custom admin for User model with profile inline."""

    inlines = (UserProfileInline,)

    # Define fieldsets that include profile-related fields
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser',
                       'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2',
                       'first_name', 'last_name', 'email'),
        }),
    )

    list_display = (
        'username',
        'first_name',
        'last_name',
        'email',
        'is_staff',
        'is_superuser',
        'is_active',
    )
    list_filter = (
        'is_staff',
        'is_superuser',
        'is_active',
    )
    search_fields = ('username', 'first_name', 'last_name', 'email')

    filter_horizontal = (
        'groups',
        'user_permissions',
    )

    # Search settings
    date_hierarchy = 'date_joined'

    # Ordering
    ordering = ('username',)