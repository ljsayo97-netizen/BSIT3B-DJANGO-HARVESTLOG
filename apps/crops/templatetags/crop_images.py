"""Template helpers for rendering crop photos."""

from django import template
from django.templatetags.static import static

from apps.crops.images import crop_image_path

register = template.Library()


@register.simple_tag
def crop_image(crop_name):
    """Return the static URL of the photo that represents ``crop_name``."""
    return static(crop_image_path(crop_name))
