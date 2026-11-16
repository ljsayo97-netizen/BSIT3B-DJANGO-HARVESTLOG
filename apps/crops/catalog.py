"""Comprehensive crop catalog for the HarvestPH crop picker.

The catalog is the single source of truth for the crop names, categories,
common Filipino names/aliases, typical days to maturity, and verified local
photo used by the crop management screens.

Crops without a verified local photo intentionally fall back to the neutral
``default.svg`` placeholder. Never point a crop at another crop's photo: a
wrong photo is worse than a clearly labelled placeholder.
"""

from __future__ import annotations

import re

VEGETABLE = "vegetable"
GRAIN = "grain"
FRUIT = "fruit"
OTHER = "other"

CATEGORY_LABELS = {
    VEGETABLE: "Vegetable",
    GRAIN: "Grain",
    FRUIT: "Fruit",
    OTHER: "Other",
}

# Display groups for the crop picker. The order here is the order shown in
# the form's datalist.
GROUP_ORDER = (
    "Rice types",
    "Cereals & grains",
    "Vegetables",
    "Leafy greens & herbs",
    "Legumes",
    "Root crops",
    "Fruits",
    "Nuts",
    "Industrial & other crops",
)


def _crop(
    name,
    category,
    days,
    *,
    aliases=(),
    image=None,
    group="",
):
    """Build one catalog entry.

    ``image`` is only the file name inside ``static/img/crops``. Entries
    without a verified photo leave it as ``None`` so the UI can show the
    neutral placeholder instead of borrowing a different crop's picture.
    """

    return {
        "name": name,
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "days_to_maturity": days,
        "aliases": tuple(aliases),
        "image": image,
        "group": group,
        "photo_title": f"{name} crop",
        "photo_alt": f"{name} crop photo",
    }


CROP_CATALOG = (
    # ---------------------------------------------------------------------
    # Rice types (all share the verified rice field photo)
    # ---------------------------------------------------------------------
    _crop("Rice", GRAIN, 110, aliases=("palay", "paddy rice", "rough rice"), image="rice.jpg", group="Rice types"),
    _crop("Brown Rice", GRAIN, 110, aliases=("unmilled rice", "cargo rice", "pinawa"), image="rice.jpg", group="Rice types"),
    _crop("Black Rice", GRAIN, 115, aliases=("purple rice", "forbidden rice", "black glutinous rice"), image="rice.jpg", group="Rice types"),
    _crop("Red Rice", GRAIN, 115, aliases=("red cargo rice",), image="rice.jpg", group="Rice types"),
    _crop("Glutinous Rice", GRAIN, 110, aliases=("sticky rice", "malagkit", "sweet rice"), image="rice.jpg", group="Rice types"),
    _crop("Aromatic Rice", GRAIN, 110, aliases=("fragrant rice", "scented rice"), image="rice.jpg", group="Rice types"),
    _crop("Jasmine Rice", GRAIN, 110, aliases=("hom mali", "jasmine"), image="rice.jpg", group="Rice types"),
    _crop("Sinandomeng Rice", GRAIN, 105, aliases=("sinandomeng",), image="rice.jpg", group="Rice types"),
    _crop("Dinorado Rice", GRAIN, 120, aliases=("dinorado",), image="rice.jpg", group="Rice types"),
    _crop("Upland Rice", GRAIN, 120, aliases=("upland palay", "dryland rice"), image="rice.jpg", group="Rice types"),
    _crop("Lowland Rice", GRAIN, 110, aliases=("lowland palay", "irrigated rice"), image="rice.jpg", group="Rice types"),
    _crop("Rainfed Rice", GRAIN, 115, aliases=("rainfed palay",), image="rice.jpg", group="Rice types"),
    # ---------------------------------------------------------------------
    # Cereals and grains
    # ---------------------------------------------------------------------
    _crop("Corn", GRAIN, 100, aliases=("maize", "mais", "sweet corn", "yellow corn", "white corn", "glutinous corn", "popcorn"), image="corn.jpg", group="Cereals & grains"),
    _crop("Wheat", GRAIN, 120, aliases=("bread wheat", "durum wheat"), image="wheat.jpg", group="Cereals & grains"),
    _crop("Sorghum", GRAIN, 110, aliases=("guinea corn", "batad"), image="sorghum.jpg", group="Cereals & grains"),
    _crop("Barley", GRAIN, 100, image="barley.jpg", group="Cereals & grains"),
    _crop("Oat", GRAIN, 100, aliases=("oats",), image="oat.jpg", group="Cereals & grains"),
    _crop("Millet", GRAIN, 90, aliases=("foxtail millet", "pearl millet"), image="millet.jpg", group="Cereals & grains"),
    _crop("Adlay", GRAIN, 120, aliases=("job's tears", "coix"), image="adlay.jpg", group="Cereals & grains"),
    _crop("Buckwheat", GRAIN, 80, image="buckwheat.jpg", group="Cereals & grains"),
    _crop("Quinoa", GRAIN, 100, image="quinoa.jpg", group="Cereals & grains"),
    # ---------------------------------------------------------------------
    # Vegetables with verified photos
    # ---------------------------------------------------------------------
    _crop("Ampalaya", VEGETABLE, 70, aliases=("bitter gourd", "bitter melon", "bittermelon", "ampalaya"), image="bittergourd.jpg", group="Vegetables"),
    _crop("Eggplant", VEGETABLE, 80, aliases=("talong", "aubergine", "brinjal"), image="eggplant.jpg", group="Vegetables"),
    _crop("Tomato", VEGETABLE, 70, aliases=("kamatis",), image="tomato.jpg", group="Vegetables"),
    _crop("Okra", VEGETABLE, 60, aliases=("lady's finger", "gumbo"), image="okra.jpg", group="Vegetables"),
    _crop("Onion", VEGETABLE, 120, aliases=("sibuyas", "red onion", "yellow onion", "white onion"), image="onion.jpg", group="Vegetables"),
    _crop("Garlic", VEGETABLE, 120, aliases=("bawang",), image="garlic.jpg", group="Vegetables"),
    _crop("Cabbage", VEGETABLE, 75, aliases=("repolyo", "green cabbage"), image="cabbage.jpg", group="Vegetables"),
    _crop("Carrot", VEGETABLE, 90, aliases=("karots", "karot"), image="carrot.jpg", group="Vegetables"),
    _crop("Pechay", VEGETABLE, 30, aliases=("pak choi", "pak choy", "bok choy"), image="pechay.jpg", group="Vegetables"),
    _crop("Lettuce", VEGETABLE, 45, aliases=("letsugas", "romaine", "iceberg lettuce"), image="lettuce.jpg", group="Vegetables"),
    _crop("Cucumber", VEGETABLE, 55, aliases=("pipino",), image="cucumber.jpg", group="Vegetables"),
    _crop("Squash", VEGETABLE, 90, aliases=("kalabasa", "pumpkin"), image="squash.jpg", group="Vegetables"),
    _crop("Potato", VEGETABLE, 100, aliases=("patatas", "irish potato"), image="potato.jpg", group="Vegetables"),
    _crop("Sweet Potato", VEGETABLE, 120, aliases=("kamote", "sweet potato"), image="sweet_potato.jpg", group="Vegetables"),
    _crop("Cassava", VEGETABLE, 300, aliases=("kamoteng kahoy", "manioc", "yuca", "balinghoy"), image="cassava.jpg", group="Root crops"),
    _crop("Mung Bean", VEGETABLE, 65, aliases=("mungbean", "munggo", "mongo", "green gram"), image="mungbean.jpg", group="Legumes"),
    _crop("Soybean", VEGETABLE, 100, aliases=("soya", "soya bean"), image="soybean.jpg", group="Legumes"),
    _crop("Peanut", VEGETABLE, 120, aliases=("mani", "groundnut"), image="peanut.jpg", group="Legumes"),
    _crop("Ginger", VEGETABLE, 240, aliases=("luya",), image="ginger.jpg", group="Leafy greens & herbs"),
    _crop("Turmeric", VEGETABLE, 270, aliases=("luyang dilaw", "kunyit"), image="turmeric.jpg", group="Leafy greens & herbs"),
    _crop("Mixed Vegetables", VEGETABLE, 60, aliases=("mixed veg", "vegetable medley"), image="vegetables.jpg", group="Vegetables"),
    # ---------------------------------------------------------------------
    # Additional vegetables
    # ---------------------------------------------------------------------
    _crop("Radish", VEGETABLE, 60, aliases=("labanos", "daikon"), image="radish.jpg", group="Root crops"),
    _crop("Beet", VEGETABLE, 60, aliases=("beetroot",), image="beet.jpg", group="Root crops"),
    _crop("Broccoli", VEGETABLE, 75, image="broccoli.jpg", group="Vegetables"),
    _crop("Cauliflower", VEGETABLE, 75, image="cauliflower.jpg", group="Vegetables"),
    _crop("Spinach", VEGETABLE, 45, aliases=("espinaka",), image="spinach.jpg", group="Leafy greens & herbs"),
    _crop("Kangkong", VEGETABLE, 30, aliases=("water spinach", "swamp cabbage", "kang kong"), image="kangkong.jpg", group="Leafy greens & herbs"),
    _crop("Mustard Greens", VEGETABLE, 40, aliases=("mustasa", "mustard"), image="mustardgreens.jpg", group="Leafy greens & herbs"),
    _crop("Chinese Cabbage", VEGETABLE, 60, aliases=("napa cabbage", "wombok"), image="chinesecabbage.jpg", group="Leafy greens & herbs"),
    _crop("Kale", VEGETABLE, 60, image="kale.jpg", group="Leafy greens & herbs"),
    _crop("Swiss Chard", VEGETABLE, 50, aliases=("chard",), image="swisschard.jpg", group="Leafy greens & herbs"),
    _crop("Moringa", VEGETABLE, 60, aliases=("malunggay", "moringa oleifera"), image="moringa.jpg", group="Leafy greens & herbs"),
    _crop("Alugbati", VEGETABLE, 50, aliases=("malabar spinach", "vine spinach"), image="alugbati.jpg", group="Leafy greens & herbs"),
    _crop("Saluyot", VEGETABLE, 45, aliases=("jute mallow", "jute leaves"), image="saluyot.jpg", group="Leafy greens & herbs"),
    _crop("Talinum", VEGETABLE, 40, aliases=("waterleaf", "talinum triangulare"), image="talinum.jpg", group="Leafy greens & herbs"),
    _crop("Celery", VEGETABLE, 90, image="celery.jpg", group="Leafy greens & herbs"),
    _crop("Parsley", VEGETABLE, 75, image="parsley.jpg", group="Leafy greens & herbs"),
    _crop("Cilantro", VEGETABLE, 50, aliases=("coriander", "wansoy"), image="cilantro.jpg", group="Leafy greens & herbs"),
    _crop("Basil", VEGETABLE, 60, aliases=("balanoi", "sweet basil"), image="basil.jpg", group="Leafy greens & herbs"),
    _crop("Mint", VEGETABLE, 45, aliases=("yerba buena", "peppermint", "spearmint"), image="mint.jpg", group="Leafy greens & herbs"),
    _crop("Oregano", VEGETABLE, 60, aliases=("suganda",), image="oregano.jpg", group="Leafy greens & herbs"),
    _crop("Lemongrass", VEGETABLE, 90, aliases=("tanglad",), image="lemongrass.jpg", group="Leafy greens & herbs"),
    _crop("Scallion", VEGETABLE, 60, aliases=("green onion", "spring onion", "sibuyas dahon"), image="scallion.jpg", group="Leafy greens & herbs"),
    _crop("Leek", VEGETABLE, 90, image="leek.jpg", group="Leafy greens & herbs"),
    _crop("Chili Pepper", VEGETABLE, 75, aliases=("chili", "sili", "siling labuyo", "hot pepper"), image="chilipepper.jpg", group="Vegetables"),
    _crop("Bell Pepper", VEGETABLE, 75, aliases=("capsicum", "sweet pepper"), image="bellpepper.jpg", group="Vegetables"),
    _crop("String Beans", VEGETABLE, 60, aliases=("sitaw", "yardlong bean", "snake bean"), image="stringbeans.jpg", group="Legumes"),
    _crop("Winged Bean", VEGETABLE, 70, aliases=("sigarilyas",), image="wingedbean.jpg", group="Legumes"),
    _crop("Hyacinth Bean", VEGETABLE, 80, aliases=("bataw",), image="hyacinthbean.jpg", group="Legumes"),
    _crop("Pigeon Pea", VEGETABLE, 120, aliases=("kadios", "kadyos"), image="pigeonpea.jpg", group="Legumes"),
    _crop("Cowpea", VEGETABLE, 70, aliases=("paayap",), image="cowpea.jpg", group="Legumes"),
    _crop("Bean Sprouts", VEGETABLE, 5, aliases=("togue", "mung bean sprouts"), image="beansprouts.jpg", group="Vegetables"),
    _crop("Chayote", VEGETABLE, 100, aliases=("sayote",), image="chayote.jpg", group="Vegetables"),
    _crop("Bottle Gourd", VEGETABLE, 70, aliases=("upo", "calabash"), image="bottlegourd.jpg", group="Vegetables"),
    _crop("Sponge Gourd", VEGETABLE, 60, aliases=("patola", "luffa"), image="spongegourd.jpg", group="Vegetables"),
    _crop("Wax Gourd", VEGETABLE, 90, aliases=("kondol", "winter melon", "ash gourd"), image="waxgourd.jpg", group="Vegetables"),
    _crop("Taro", VEGETABLE, 180, aliases=("gabi", "dasheen"), image="taro.jpg", group="Root crops"),
    _crop("Ube", VEGETABLE, 240, aliases=("purple yam",), image="ube.jpg", group="Root crops"),
    _crop("Yam", VEGETABLE, 240, aliases=("tugi", "true yam"), image="yam.jpg", group="Root crops"),
    _crop("Arrowroot", VEGETABLE, 240, aliases=("uraro",), image="arrowroot.jpg", group="Root crops"),
    _crop("Jicama", VEGETABLE, 120, aliases=("singkamas", "yam bean"), image="jicama.jpg", group="Root crops"),
    _crop("Yacon", VEGETABLE, 180, image="yacon.jpg", group="Root crops"),
    _crop("Turnip", VEGETABLE, 60, image="turnip.jpg", group="Root crops"),
    _crop("Asparagus", VEGETABLE, 180, image="asparagus.jpg", group="Vegetables"),
    _crop("Artichoke", VEGETABLE, 120, aliases=("globe artichoke",), image="artichoke.jpg", group="Vegetables"),
    _crop("Brussels Sprouts", VEGETABLE, 90, image="brusselssprouts.jpg", group="Vegetables"),
    _crop("Arugula", VEGETABLE, 40, aliases=("rocket", "rugula"), image="arugula.jpg", group="Leafy greens & herbs"),
    _crop("Watercress", VEGETABLE, 45, image="watercress.jpg", group="Leafy greens & herbs"),
    _crop("Endive", VEGETABLE, 60, image="endive.jpg", group="Leafy greens & herbs"),
    _crop("Fennel", VEGETABLE, 90, image="fennel.jpg", group="Leafy greens & herbs"),
    _crop("Mushroom", OTHER, 30, aliases=("kabute", "oyster mushroom", "shiitake", "button mushroom"), image="mushroom.jpg", group="Industrial & other crops"),
    # ---------------------------------------------------------------------
    # Fruits with verified photos
    # ---------------------------------------------------------------------
    _crop("Banana", FRUIT, 270, aliases=("saging", "saba", "lakatan", "latundan", "cavendish"), image="banana.jpg", group="Fruits"),
    _crop("Mango", FRUIT, 120, aliases=("mangga", "carabao mango", "piko mango"), image="mango.jpg", group="Fruits"),
    _crop("Grapes", FRUIT, 120, aliases=("grape", "ubas"), image="grapes.jpg", group="Fruits"),
    _crop("Watermelon", FRUIT, 80, aliases=("pakwan",), image="watermelon.jpg", group="Fruits"),
    _crop("Melon", FRUIT, 80, aliases=("cantaloupe", "honeydew", "muskmelon", "musk melon", "rockmelon"), image="melon.jpg", group="Fruits"),
    _crop("Lanzones", FRUIT, 365, aliases=("lansones", "lanzon"), image="lanzones.jpg", group="Fruits"),
    _crop("Pineapple", FRUIT, 540, aliases=("pinya",), image="pineapple.jpg", group="Fruits"),
    _crop("Coconut", FRUIT, 365, aliases=("niyog", "buko"), image="coconut.jpg", group="Fruits"),
    # ---------------------------------------------------------------------
    # Additional fruits
    # ---------------------------------------------------------------------
    _crop("Papaya", FRUIT, 270, aliases=("kapayas",), image="papaya.jpg", group="Fruits"),
    _crop("Avocado", FRUIT, 365, aliases=("abokado",), image="avocado.jpg", group="Fruits"),
    _crop("Guava", FRUIT, 240, aliases=("bayabas",), image="guava.jpg", group="Fruits"),
    _crop("Rambutan", FRUIT, 365, image="rambutan.jpg", group="Fruits"),
    _crop("Durian", FRUIT, 365, image="durian.jpg", group="Fruits"),
    _crop("Mangosteen", FRUIT, 365, image="mangosteen.jpg", group="Fruits"),
    _crop("Jackfruit", FRUIT, 365, aliases=("langka", "nangka"), image="jackfruit.jpg", group="Fruits"),
    _crop("Santol", FRUIT, 365, aliases=("cotton fruit",), image="santol.jpg", group="Fruits"),
    _crop("Sugar Apple", FRUIT, 240, aliases=("atis", "sweetsop"), image="sugarapple.jpg", group="Fruits"),
    _crop("Soursop", FRUIT, 240, aliases=("guyabano", "graviola"), image="soursop.jpg", group="Fruits"),
    _crop("Star Apple", FRUIT, 240, aliases=("caimito",), image="starapple.jpg", group="Fruits"),
    _crop("Sapodilla", FRUIT, 240, aliases=("chico", "zapote"), image="sapodilla.jpg", group="Fruits"),
    _crop("Rose Apple", FRUIT, 240, aliases=("makopa",), image="roseapple.jpg", group="Fruits"),
    _crop("Java Plum", FRUIT, 240, aliases=("duhat", "black plum"), image="javaplum.jpg", group="Fruits"),
    _crop("Spanish Plum", FRUIT, 240, aliases=("siniguelas", "red mombin"), image="spanishplum.jpg", group="Fruits"),
    _crop("Bilimbi", FRUIT, 180, aliases=("kamias", "cucumber tree"), image="bilimbi.jpg", group="Fruits"),
    _crop("Starfruit", FRUIT, 180, aliases=("balimbing", "carambola"), image="starfruit.jpg", group="Fruits"),
    _crop("Calamansi", FRUIT, 180, aliases=("calamondin", "kalamansi", "philippine lime"), image="calamansi.jpg", group="Fruits"),
    _crop("Pomelo", FRUIT, 240, aliases=("suha", "pummelo"), image="pomelo.jpg", group="Fruits"),
    _crop("Orange", FRUIT, 240, aliases=("sweet orange",), image="orange.jpg", group="Fruits"),
    _crop("Dalandan", FRUIT, 180, aliases=("dalanghita", "sour orange"), image="dalandan.jpg", group="Fruits"),
    _crop("Lemon", FRUIT, 180, image="lemon.jpg", group="Fruits"),
    _crop("Lime", FRUIT, 180, aliases=("dayap", "key lime"), image="lime.jpg", group="Fruits"),
    _crop("Grapefruit", FRUIT, 240, aliases=("pomelo hybrid",), image="grapefruit.jpg", group="Fruits"),
    _crop("Dragon Fruit", FRUIT, 365, aliases=("pitaya",), image="dragonfruit.jpg", group="Fruits"),
    _crop("Passion Fruit", FRUIT, 240, aliases=("passionfruit",), image="passionfruit.jpg", group="Fruits"),
    _crop("Strawberry", FRUIT, 120, image="strawberry.jpg", group="Fruits"),
    _crop("Blueberry", FRUIT, 365, image="blueberry.jpg", group="Fruits"),
    _crop("Raspberry", FRUIT, 365, image="raspberry.jpg", group="Fruits"),
    _crop("Blackberry", FRUIT, 365, image="blackberry.jpg", group="Fruits"),
    _crop("Kiwi", FRUIT, 365, aliases=("kiwifruit",), image="kiwi.jpg", group="Fruits"),
    _crop("Pomegranate", FRUIT, 365, aliases=("granada",), image="pomegranate.jpg", group="Fruits"),
    _crop("Persimmon", FRUIT, 365, image="persimmon.jpg", group="Fruits"),
    _crop("Fig", FRUIT, 365, image="fig.jpg", group="Fruits"),
    _crop("Breadfruit", FRUIT, 365, aliases=("rimas",), image="breadfruit.jpg", group="Fruits"),
    _crop("Marang", FRUIT, 365, image="marang.jpg", group="Fruits"),
    _crop("Longan", FRUIT, 365, image="longan.jpg", group="Fruits"),
    _crop("Lychee", FRUIT, 365, aliases=("litchi",), image="lychee.jpg", group="Fruits"),
    _crop("Salak", FRUIT, 365, aliases=("snake fruit",), image="salak.jpg", group="Fruits"),
    _crop("Bignay", FRUIT, 365, image="bignay.jpg", group="Fruits"),
    _crop("Lipote", FRUIT, 365, image="lipote.jpg", group="Fruits"),
    _crop("Apple", FRUIT, 365, image="apple.jpg", group="Fruits"),
    _crop("Pear", FRUIT, 365, image="pear.jpg", group="Fruits"),
    _crop("Peach", FRUIT, 365, image="peach.jpg", group="Fruits"),
    _crop("Plum", FRUIT, 365, image="plum.jpg", group="Fruits"),
    _crop("Cherry", FRUIT, 365, image="cherry.jpg", group="Fruits"),
    # ---------------------------------------------------------------------
    # Nuts
    # ---------------------------------------------------------------------
    _crop("Cashew", OTHER, 365, aliases=("kasuy",), image="cashew.jpg", group="Nuts"),
    _crop("Pili Nut", OTHER, 365, aliases=("pili",), image="pilinut.jpg", group="Nuts"),
    _crop("Macadamia", OTHER, 365, image="macadamia.jpg", group="Nuts"),
    _crop("Walnut", OTHER, 365, image="walnut.jpg", group="Nuts"),
    _crop("Almond", OTHER, 365, image="almond.jpg", group="Nuts"),
    # ---------------------------------------------------------------------
    # Industrial and other crops
    # ---------------------------------------------------------------------
    _crop("Sugarcane", OTHER, 330, aliases=("sugar cane", "tubo"), image="sugarcane.jpg", group="Industrial & other crops"),
    _crop("Tobacco", OTHER, 120, aliases=("tabako",), image="tobacco.jpg", group="Industrial & other crops"),
    _crop("Cacao", OTHER, 180, aliases=("kakaw", "cocoa"), image="cacao.jpg", group="Industrial & other crops"),
    _crop("Coffee", OTHER, 240, aliases=("kape", "arabica", "robusta"), image="coffee.jpg", group="Industrial & other crops"),
    _crop("Rubber", OTHER, 1825, aliases=("goma", "para rubber"), image="rubber.jpg", group="Industrial & other crops"),
    _crop("Abaca", OTHER, 540, aliases=("manila hemp",), image="abaca.jpg", group="Industrial & other crops"),
    _crop("Cotton", OTHER, 180, image="cotton.jpg", group="Industrial & other crops"),
    _crop("Oil Palm", OTHER, 1095, aliases=("palm oil",), image="oilpalm.jpg", group="Industrial & other crops"),
    _crop("Bamboo", OTHER, 365, image="bamboo.jpg", group="Industrial & other crops"),
    _crop("Jatropha", OTHER, 365, image="jatropha.jpg", group="Industrial & other crops"),
    _crop("Napier Grass", OTHER, 60, aliases=("napier", "elephant grass"), image="napiergrass.jpg", group="Industrial & other crops"),
)

# Freeze the calculated fields so templates and callers can rely on them.
for _entry in CROP_CATALOG:
    _entry["has_photo"] = bool(_entry["image"])

_BY_NAME = {entry["name"].casefold(): entry for entry in CROP_CATALOG}

_ALIAS_INDEX = []
for _entry in CROP_CATALOG:
    _ALIAS_INDEX.append((_entry["name"].casefold(), _entry))
    for _alias in _entry["aliases"]:
        _ALIAS_INDEX.append((_alias.casefold(), _entry))
# Longest names first so "sweet potato" wins over "potato" and "watermelon"
# wins over "melon" when a longer alias is present in the query.
_ALIAS_INDEX.sort(key=lambda item: len(item[0]), reverse=True)


def normalize_crop_name(name):
    """Return a stable, lower-case crop name for comparisons."""

    return " ".join((name or "").casefold().split())


def _contains_whole_words(text, phrase):
    """True when ``phrase`` appears in ``text`` as a separate word/phrase."""

    if not phrase:
        return False
    return re.search(
        r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])",
        text,
    ) is not None


def _singular_candidates(normalized):
    """Yield common singular forms of a crop name.

    Growers often type plurals such as "Potatoes", "Sweet Potatoes", or
    "Tomatoes". Trying the singular form keeps the photo, category, and
    maturity lookups working without duplicating every alias in the catalog.
    """

    yield normalized
    if normalized.endswith("ies") and len(normalized) > 3:
        yield normalized[:-3] + "y"
    if normalized.endswith("oes") and len(normalized) > 3:
        yield normalized[:-2]
    if normalized.endswith("es") and len(normalized) > 2:
        yield normalized[:-2]
    if normalized.endswith("s") and len(normalized) > 2:
        yield normalized[:-1]


def find_catalog_entry(name):
    """Resolve a crop name or common alias to its catalog entry.

    Resolution order:
    1. exact crop name (including common plural forms),
    2. exact alias (including common plural forms),
    3. the longest catalog name/alias that appears as whole words in the
       supplied name (so "Rice (NSIC Rc 222)" resolves to Rice, while
       "Sweet Potato" resolves to Sweet Potato rather than Potato).
    """

    normalized = normalize_crop_name(name)
    if not normalized:
        return None

    candidates = tuple(dict.fromkeys(_singular_candidates(normalized)))

    for candidate in candidates:
        exact = _BY_NAME.get(candidate)
        if exact:
            return exact

    for candidate in candidates:
        for alias, entry in _ALIAS_INDEX:
            if alias == candidate:
                return entry

    for candidate in candidates:
        for alias, entry in _ALIAS_INDEX:
            if _contains_whole_words(candidate, alias):
                return entry

    return None


def catalog_names():
    """Return all canonical crop names in catalog order."""

    return tuple(entry["name"] for entry in CROP_CATALOG)


def catalog_for_category(category):
    """Return catalog entries for a category value."""

    return tuple(entry for entry in CROP_CATALOG if entry["category"] == category)


def catalog_stats():
    """Return total and per-category counts for the crop picker hint."""

    stats = {category: 0 for category in CATEGORY_LABELS}
    for entry in CROP_CATALOG:
        stats[entry["category"]] += 1
    stats["total"] = len(CROP_CATALOG)
    return stats


def catalog_group_sort_key(entry):
    """Sort key used to display catalog entries by group then name."""

    try:
        position = GROUP_ORDER.index(entry["group"])
    except ValueError:
        position = len(GROUP_ORDER)
    return (position, entry["name"].casefold())
