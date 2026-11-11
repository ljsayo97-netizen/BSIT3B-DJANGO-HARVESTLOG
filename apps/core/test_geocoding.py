from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from .geocoding import (
    geocode_ph_location,
    parse_location,
    place_names_match,
)


ILOG_VILLAGE = {
    'osm_type': 'node',
    'lat': '9.9943517',
    'lon': '122.7568494',
    'type': 'village',
    'addresstype': 'village',
    'name': 'Vista Alegre',
    'display_name': (
        'Vista Alegre, Ilog, Negros Occidental, Negros Island Region, '
        '6109, Philippines'
    ),
    'address': {
        'village': 'Vista Alegre',
        'town': 'Ilog',
        'state': 'Negros Occidental',
        'region': 'Negros Island Region',
        'postcode': '6109',
        'country': 'Philippines',
        'country_code': 'ph',
    },
}

BACOLOD_VILLAGE = {
    'osm_type': 'node',
    'lat': '10.6430819',
    'lon': '123.0062875',
    'type': 'village',
    'addresstype': 'village',
    'name': 'Vista Alegre',
    'display_name': 'Vista Alegre, Bacolod, Negros Island Region, Philippines',
    'address': {
        'village': 'Vista Alegre',
        'city': 'Bacolod',
        'region': 'Negros Island Region',
        'postcode': '6100',
        'country': 'Philippines',
        'country_code': 'ph',
    },
}

ILOG_TOWN = {
    'osm_type': 'relation',
    'lat': '10.0242067',
    'lon': '122.7691808',
    'type': 'administrative',
    'addresstype': 'town',
    'name': 'Ilog',
    'display_name': (
        'Ilog, Negros Occidental, Negros Island Region, 6109, Philippines'
    ),
    'address': {
        'town': 'Ilog',
        'state': 'Negros Occidental',
        'region': 'Negros Island Region',
        'country': 'Philippines',
        'country_code': 'ph',
    },
}

CAMUGAO_VILLAGE = {
    'osm_type': 'relation',
    'lat': '9.9865232',
    'lon': '122.8095880',
    'type': 'administrative',
    'addresstype': 'village',
    'name': 'Camugao',
    'display_name': (
        'Camugao, Kabankalan, Negros Occidental, Negros Island Region, '
        '6111, Philippines'
    ),
    'geojson': {
        'type': 'Polygon',
        'coordinates': [[
            [122.7978821, 9.9602182],
            [122.8158403, 9.9602182],
            [122.8158403, 9.9923821],
            [122.7978821, 9.9923821],
            [122.7978821, 9.9602182],
        ]],
    },
    'address': {
        'village': 'Camugao',
        'city': 'Kabankalan',
        'state': 'Negros Occidental',
        'region': 'Negros Island Region',
        'country': 'Philippines',
        'country_code': 'ph',
    },
}


class LocationParsingTests(TestCase):
    def test_barangay_municipality_province_order_is_preserved(self):
        parsed = parse_location('Vista Alegre, Ilog, Negros Occidental')

        self.assertEqual(parsed['barangay'], 'Vista Alegre')
        self.assertEqual(parsed['municipality'], 'Ilog')
        self.assertEqual(parsed['province'], 'Negros Occidental')

    def test_country_and_postal_code_are_ignored(self):
        parsed = parse_location(
            'Vista Alegre, Ilog, Negros Occidental, 6109, Philippines'
        )

        self.assertEqual(parsed['barangay'], 'Vista Alegre')
        self.assertEqual(parsed['municipality'], 'Ilog')
        self.assertEqual(parsed['province'], 'Negros Occidental')

    def test_barangay_prefix_is_removed(self):
        parsed = parse_location(
            'Brgy. Vista Alegre, Ilog, Negros Occidental'
        )

        self.assertEqual(parsed['barangay'], 'Vista Alegre')

    def test_two_part_barangay_and_city(self):
        parsed = parse_location('Brgy. 5, Kabankalan City')

        self.assertEqual(parsed['barangay'], '5')
        self.assertEqual(parsed['municipality'], 'Kabankalan City')
        self.assertEqual(parsed['province'], '')

    def test_missing_comma_between_municipality_and_province(self):
        parsed = parse_location('Vista Alegre, Ilog Negros Occidental')

        self.assertEqual(parsed['barangay'], 'Vista Alegre')
        self.assertEqual(parsed['municipality'], 'Ilog')
        self.assertEqual(parsed['province'], 'Negros Occidental')

    def test_names_tolerate_common_spelling_mistakes(self):
        self.assertTrue(
            place_names_match('Negros Ociddental', 'Negros Occidental')
        )
        self.assertFalse(place_names_match('Ilog', 'Iloilo'))


class HierarchicalGeocodingTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch('apps.core.geocoding._nominatim_search')
    def test_searches_the_full_hierarchy(self, search):
        search.return_value = [ILOG_VILLAGE]

        result = geocode_ph_location(
            'Vista Alegre, Ilog, Negros Occidental'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Vista Alegre, Ilog, Negros Occidental')
        self.assertEqual(result['level'], 'barangay')
        self.assertEqual(result['municipality'], 'Ilog')
        self.assertEqual(result['province'], 'Negros Occidental')
        self.assertAlmostEqual(result['latitude'], 9.994352, places=6)
        self.assertAlmostEqual(result['longitude'], 122.756849, places=6)
        search.assert_called_once()
        self.assertEqual(
            search.call_args.args[0],
            'Vista Alegre, Ilog, Negros Occidental, Philippines',
        )

    @patch('apps.core.geocoding._nominatim_search')
    def test_geocodes_when_the_municipality_and_province_lack_a_comma(
        self, search
    ):
        search.return_value = [ILOG_VILLAGE]

        result = geocode_ph_location('Vista Alegre, Ilog Negros Occidental')

        self.assertIsNotNone(result)
        self.assertEqual(result['barangay'], 'Vista Alegre')
        self.assertEqual(result['municipality'], 'Ilog')
        self.assertEqual(result['province'], 'Negros Occidental')
        self.assertEqual(
            search.call_args.args[0],
            'Vista Alegre, Ilog, Negros Occidental, Philippines',
        )

    @patch('apps.core.geocoding._nominatim_search')
    def test_returns_the_exact_matched_barangay_and_its_boundary(self, search):
        search.return_value = [CAMUGAO_VILLAGE]

        result = geocode_ph_location(
            'Brgy. Camugao, Kabankalan City, Negros Occidental'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['level'], 'barangay')
        self.assertEqual(result['barangay'], 'Camugao')
        self.assertEqual(result['matched_barangay'], 'Camugao')
        self.assertEqual(
            result['barangay_boundary'], CAMUGAO_VILLAGE['geojson']
        )
        self.assertAlmostEqual(result['latitude'], 9.986523, places=6)
        self.assertAlmostEqual(result['longitude'], 122.809588, places=6)

    @patch('apps.core.geocoding._nominatim_search')
    def test_rejects_a_same_named_barangay_in_another_city(self, search):
        def side_effect(query, timeout=None):
            if query.startswith('Vista Alegre, Ilog, Negros Occidental'):
                return [BACOLOD_VILLAGE]
            if query == 'Vista Alegre, Ilog, Philippines':
                return [ILOG_VILLAGE]
            return []

        search.side_effect = side_effect

        result = geocode_ph_location(
            'Vista Alegre, Ilog, Negros Occidental'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['municipality'], 'Ilog')
        self.assertAlmostEqual(result['latitude'], 9.994352, places=6)
        self.assertEqual(search.call_count, 2)

    @patch('apps.core.geocoding._nominatim_search')
    def test_province_typo_falls_back_to_barangay_and_municipality(
        self, search
    ):
        def side_effect(query, timeout=None):
            if 'Ociddental' in query:
                return []
            if query == 'Vista Alegre, Ilog, Philippines':
                return [ILOG_VILLAGE]
            return []

        search.side_effect = side_effect

        result = geocode_ph_location(
            'Vista Alegre, Ilog, Negros Ociddental'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['municipality'], 'Ilog')
        self.assertAlmostEqual(result['latitude'], 9.994352, places=6)

    @patch('apps.core.geocoding._nominatim_search')
    def test_falls_back_to_the_municipality_center(self, search):
        def side_effect(query, timeout=None):
            if query == 'Ilog, Negros Occidental, Philippines':
                return [ILOG_TOWN]
            return []

        search.side_effect = side_effect

        result = geocode_ph_location(
            'Vista Alegre, Ilog, Negros Occidental'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result['level'], 'municipality')
        self.assertEqual(result['name'], 'Ilog, Negros Occidental')
        self.assertEqual(result['matched_barangay'], '')
        self.assertIsNone(result['barangay_boundary'])
        self.assertAlmostEqual(result['latitude'], 10.024207, places=6)

    @patch('apps.core.geocoding._nominatim_search')
    def test_results_are_cached(self, search):
        search.return_value = [ILOG_VILLAGE]

        first = geocode_ph_location(
            'Vista Alegre, Ilog, Negros Occidental'
        )
        second = geocode_ph_location(
            'Vista Alegre, Ilog, Negros Occidental'
        )

        self.assertEqual(first, second)
        self.assertEqual(search.call_count, 1)
