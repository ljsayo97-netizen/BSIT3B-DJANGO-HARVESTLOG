"""Template context for crop readiness notifications."""

from .services import (
    get_notifications,
    get_ready_crop_count,
    get_unread_notification_count,
    sync_harvest_readiness,
)


def harvest_notifications(request):
    """Keep readiness current and expose notification data to every page."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}

    sync_harvest_readiness(user)
    return {
        'harvest_unread_count': get_unread_notification_count(user),
        'harvest_unread_notifications': get_notifications(
            user, unread_only=True, limit=5
        ),
        'harvest_ready_count': get_ready_crop_count(user),
    }
