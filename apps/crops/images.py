"""Crop photos used in the crop management interface."""

CROP_IMAGE_FALLBACK = 'img/crops/default.svg'

# Each rule maps a crop and its common names (English and Filipino) to the
# photo shown in the crop list. More specific crops must come before broader
# ones (e.g. sweet potato before potato, turmeric before ginger) because crop
# names are matched by keyword.
CROP_IMAGE_RULES = (
    (('rice', 'palay'), 'img/crops/rice.jpg'),
    (('corn', 'mais', 'maize'), 'img/crops/corn.jpg'),
    (('sugarcane', 'sugar cane', 'tubo'), 'img/crops/sugarcane.jpg'),
    (('peanut', 'groundnut', 'mani'), 'img/crops/peanut.jpg'),
    (('watermelon', 'pakwan'), 'img/crops/watermelon.jpg'),
    (('melon', 'cantaloupe'), 'img/crops/melon.jpg'),
    (('lanzones', 'lansones', 'lanzon'), 'img/crops/lanzones.jpg'),
    (('banana', 'saging'), 'img/crops/banana.jpg'),
    (('mango', 'mangga'), 'img/crops/mango.jpg'),
    (('coconut', 'niyog'), 'img/crops/coconut.jpg'),
    (('pineapple', 'pinya'), 'img/crops/pineapple.jpg'),
    (('tomato', 'kamatis'), 'img/crops/tomato.jpg'),
    (('eggplant', 'aubergine', 'talong'), 'img/crops/eggplant.jpg'),
    (('okra',), 'img/crops/okra.jpg'),
    (('onion', 'sibuyas'), 'img/crops/onion.jpg'),
    (('garlic', 'bawang'), 'img/crops/garlic.jpg'),
    (('cabbage', 'repolyo'), 'img/crops/cabbage.jpg'),
    (('carrot', 'karots'), 'img/crops/carrot.jpg'),
    # Cassava before sweet potato so "kamoteng kahoy" is not read as "kamote".
    (('cassava', 'kamoteng kahoy', 'manioc'), 'img/crops/cassava.jpg'),
    (('sweet potato', 'kamote'), 'img/crops/sweet_potato.jpg'),
    (('potato', 'patatas'), 'img/crops/potato.jpg'),
    (('coffee', 'kape'), 'img/crops/coffee.jpg'),
    (('cacao', 'cocoa', 'kakaw'), 'img/crops/cacao.jpg'),
    (('mung bean', 'mungbean', 'munggo', 'mongo', 'green gram'), 'img/crops/mungbean.jpg'),
    (('soybean', 'soya'), 'img/crops/soybean.jpg'),
    (('cucumber', 'pipino'), 'img/crops/cucumber.jpg'),
    (('squash', 'kalabasa', 'pumpkin'), 'img/crops/squash.jpg'),
    ((
        'bitter gourd', 'bitter melon', 'bittermelon', 'ampalaya',
    ), 'img/crops/bittergourd.jpg'),
    (('pechay', 'pak choi', 'pak choy', 'bok choy'), 'img/crops/pechay.jpg'),
    (('lettuce', 'letsugas'), 'img/crops/lettuce.jpg'),
    # Turmeric before ginger so "luyang dilaw" is not read as "luya".
    (('turmeric', 'luyang dilaw'), 'img/crops/turmeric.jpg'),
    (('ginger', 'luya'), 'img/crops/ginger.jpg'),
    (('tobacco', 'tabako'), 'img/crops/tobacco.jpg'),
    (
        (
            'vegetable', 'spinach', 'kangkong', 'radish', 'labanos', 'beet',
            'broccoli', 'cauliflower', 'pepper', 'chili', 'sili', 'bean',
            'mustard', 'mustasa',
        ),
        'img/crops/vegetables.jpg',
    ),
)


def crop_image_path(crop_name):
    """Return the static path of the image that represents ``crop_name``."""
    normalized = ' '.join((crop_name or '').lower().split())
    for keywords, image_path in CROP_IMAGE_RULES:
        if any(keyword in normalized for keyword in keywords):
            return image_path
    return CROP_IMAGE_FALLBACK
