"""Template context for crop readiness notifications."""

from .services import (
    get_topbar_notifications,
    get_unread_notification_count,
    sync_harvest_readiness,
)


def harvest_notifications(request):
    """Keep readiness current and expose notification data to the topbar."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}

    sync_harvest_readiness(user)
    return {
        'harvest_unread_count': get_unread_notification_count(user),
        'topbar_notifications': get_topbar_notifications(user, limit=6),
    }
