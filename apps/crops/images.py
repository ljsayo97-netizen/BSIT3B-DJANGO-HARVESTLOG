"""Crop photos used in the crop management interface."""

from .catalog import CROP_CATALOG, find_catalog_entry

CROP_IMAGE_FALLBACK = "img/crops/default.svg"


def _build_crop_image_rules():
    """Build keyword-to-photo rules from the verified crop catalog.

    Multiple catalog crops can share the same verified photo (for example all
    rice types share ``rice.jpg``). Keywords from those entries are merged so
    a rule always points at the photo of the same crop, never at another
    crop's picture.

    Rules are sorted by their longest keyword so that more specific names
    such as "sweet potato" win over "potato" and "watermelon" wins over
    "melon" in the browser-side substring matcher.
    """

    grouped = {}
    for entry in CROP_CATALOG:
        image = entry.get("image")
        if not image:
            continue
        keywords = grouped.setdefault(image, [])
        for name in (entry["name"], *entry["aliases"]):
            lowered = name.casefold()
            if lowered not in keywords:
                keywords.append(lowered)

    rules = [
        (tuple(keywords), f"img/crops/{image}")
        for image, keywords in grouped.items()
    ]
    rules.sort(key=lambda rule: max(len(keyword) for keyword in rule[0]), reverse=True)
    return tuple(rules)


# Each rule maps a crop and its common names (English and Filipino) to the
# photo shown in the crop list. Only existing, verified crop photos are
# included; a crop without a specific photo uses the neutral placeholder.
CROP_IMAGE_RULES = _build_crop_image_rules()


def crop_image_path(crop_name):
    """Return the static path of the image that represents ``crop_name``."""

    entry = find_catalog_entry(crop_name)
    if entry and entry.get("image"):
        return f"img/crops/{entry['image']}"
    return CROP_IMAGE_FALLBACK


def is_verified_local_crop_image(image_url, crop_name):
    """Check whether a local crop photo belongs to ``crop_name``.

    The crop form can keep a previously selected photo in the browser when
    the grower changes the crop name. This server-side guard ensures a local
    static photo from a different crop (for example a sweet potato photo
    saved on a watermelon crop) is never persisted.
    """

    if not image_url:
        return True

    prefix = "/static/img/crops/"
    if not image_url.startswith(prefix):
        # Remote search results and uploaded media cannot be compared by path.
        return True

    expected = f"/static/{crop_image_path(crop_name)}"
    return image_url.split("?", 1)[0] == expected
