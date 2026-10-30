from decimal import Decimal
from urllib.error import URLError
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.farms.models import Farm

from .weather import (
    _build_advice,
    build_weather_widget,
    geocode_location,
)


GEOCODE_PAYLOAD = {
    'results': [
        {
            'name': 'North Field',
            'admin1': 'Ohio',
            'country': 'United States',
            'country_code': 'US',
            'latitude': 39.5,
            'longitude': -84.4,
        },
        {
            'name': 'Davao City',
            'admin1': 'Davao Region',
            'country': 'Philippines',
            'country_code': 'PH',
            'latitude': 7.2233,
            'longitude': 125.5782,
        },
    ],
}

US_ONLY_PAYLOAD = {
    'results': [
        {
            'name': 'North Field',
            'admin1': 'Ohio',
            'country': 'United States',
            'country_code': 'US',
            'latitude': 39.5,
            'longitude': -84.4,
        },
    ],
}

KABANKALAN_PAYLOAD = {
    'results': [
        {
            'name': 'Kabankalan',
            'admin1': 'Western Visayas',
            'country': 'Philippines',
            'country_code': 'PH',
            'latitude': 9.989,
            'longitude': 122.814,
        },
    ],
}

FORECAST_PAYLOAD = {
    'timezone': 'Asia/Manila',
    'current': {
        'time': '2026-10-28T10:00',
        'temperature_2m': 31.6,
        'relative_humidity_2m': 55,
        'apparent_temperature': 34.4,
        'is_day': 1,
        'precipitation': 0,
        'weather_code': 3,
        'wind_speed_10m': 12.2,
        'wind_gusts_10m': 32.8,
    },
    'daily': {
        'time': [
            '2026-10-28',
            '2026-10-29',
            '2026-10-30',
            '2026-10-31',
            '2026-11-01',
        ],
        'weather_code': [3, 61, 95, 2, 0],
        'temperature_2m_max': [34.8, 33.7, 33.0, 32.7, 31.8],
        'temperature_2m_min': [27.9, 27.8, 27.1, 25.8, 25.3],
        'precipitation_probability_max': [41, 84, 100, 97, 91],
        'precipitation_sum': [0.1, 2.2, 3.0, 5.3, 3.6],
        'wind_speed_10m_max': [14.6, 14.0, 9.0, 11.0, 9.2],
    },
}


def _request_side_effect(url, params, timeout=None):
    if 'geocoding' in url:
        return GEOCODE_PAYLOAD
    return FORECAST_PAYLOAD


class WeatherServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch('apps.core.weather._request_json')
    def test_geocode_prefers_the_configured_country(self, request_json):
        request_json.return_value = GEOCODE_PAYLOAD

        location = geocode_location('Davao City')

        self.assertEqual(location['country_code'], 'PH')
        self.assertEqual(
            location['name'],
            'Davao City, Davao Region, Philippines',
        )

    @patch('apps.core.weather._request_json')
    def test_geocode_rejects_a_wrong_country_result(self, request_json):
        request_json.return_value = US_ONLY_PAYLOAD

        self.assertIsNone(geocode_location('North Field'))

    @patch('apps.core.weather._request_json')
    def test_geocode_results_are_cached(self, request_json):
        request_json.return_value = GEOCODE_PAYLOAD

        geocode_location('Davao City')
        geocode_location('Davao City')

        self.assertEqual(request_json.call_count, 1)

    @patch('apps.core.weather._request_json')
    def test_geocode_simplifies_detailed_locations(self, request_json):
        def side_effect(url, params, timeout=None):
            if params['name'] == 'Kabankalan City':
                return KABANKALAN_PAYLOAD
            return {'results': []}

        request_json.side_effect = side_effect

        location = geocode_location(
            'Brgy. 1, Kabankalan City, Negros Occidental'
        )

        self.assertEqual(
            location['name'],
            'Kabankalan, Western Visayas, Philippines',
        )
        self.assertEqual(request_json.call_count, 2)

    @patch(
        'apps.core.weather._request_json',
        side_effect=URLError('offline'),
    )
    def test_geocode_failures_are_cached(self, request_json):
        self.assertIsNone(geocode_location('Davao City'))
        self.assertIsNone(geocode_location('Davao City'))

        self.assertEqual(request_json.call_count, 1)


class WeatherWidgetBuilderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='weather-owner',
            password='secret1234',
        )
        self.farm = Farm.objects.create(
            user=self.user,
            name='Green Valley Farm',
            owner='Mia Santos',
            location='Davao City',
            size_hectares=Decimal('12.50'),
            date_registered=timezone.now(),
        )

    def tearDown(self):
        cache.clear()

    @patch('apps.core.weather._request_json')
    def test_widget_uses_the_primary_farm_location(self, request_json):
        request_json.side_effect = _request_side_effect

        weather = build_weather_widget(self.user)

        self.assertTrue(weather['available'])
        self.assertFalse(weather['location']['is_default'])
        self.assertEqual(
            weather['location']['name'],
            'Davao City, Davao Region, Philippines',
        )
        self.assertEqual(weather['location']['farm_name'], 'Green Valley Farm')
        self.assertEqual(weather['current']['temperature'], 31.6)
        self.assertEqual(weather['current']['observed_at'], '10:00 AM')
        self.assertEqual(len(weather['daily']), 4)
        self.assertEqual(weather['daily'][0]['day_label'], 'Today')
        self.assertEqual(weather['daily'][1]['day_label'], 'Tomorrow')
        self.assertEqual(weather['daily'][2]['day_label'], 'Fri')
        self.assertEqual(weather['daily'][0]['date_label'], 'Oct 28')
        self.assertTrue(weather['advice'])

    @patch('apps.core.weather._request_json')
    def test_widget_falls_back_to_the_default_location(self, request_json):
        self.farm.location = 'North Field'
        self.farm.save(update_fields=['location'])

        def side_effect(url, params, timeout=None):
            if 'geocoding' in url:
                return US_ONLY_PAYLOAD
            return FORECAST_PAYLOAD

        request_json.side_effect = side_effect

        weather = build_weather_widget(self.user)

        self.assertTrue(weather['location']['is_default'])
        self.assertEqual(weather['location']['name'], 'Manila, Philippines')

    @patch(
        'apps.core.weather._request_json',
        side_effect=URLError('offline'),
    )
    def test_widget_reports_unavailable_weather(self, request_json):
        weather = build_weather_widget(self.user)

        self.assertFalse(weather['available'])
        self.assertEqual(weather['source'], 'Open-Meteo')


class WeatherAdviceTests(TestCase):
    def _current(self, **overrides):
        current = {'humidity': 60, 'temperature': 30}
        current.update(overrides)
        return current

    def _day(self, **overrides):
        day = {
            'rain_probability': 0,
            'rain_sum': 0,
            'wind_max': 10,
            'max': 31,
            'min': 24,
        }
        day.update(overrides)
        return day

    def test_heavy_rain_advice(self):
        advice = _build_advice(
            self._current(),
            [self._day(rain_probability=95)],
        )

        self.assertEqual(advice[0]['tone'], 'danger')
        self.assertIn('Heavy rain', advice[0]['title'])

    def test_heat_stress_advice(self):
        advice = _build_advice(self._current(), [self._day(max=36)])

        self.assertTrue(
            any('Heat stress' in tip['title'] for tip in advice)
        )

    def test_strong_wind_advice(self):
        advice = _build_advice(self._current(), [self._day(wind_max=35)])

        self.assertTrue(any('Strong winds' in tip['title'] for tip in advice))

    def test_humid_conditions_raise_disease_advice(self):
        advice = _build_advice(
            self._current(humidity=92, temperature=27),
            [self._day()],
        )

        self.assertTrue(
            any('disease pressure' in tip['title'] for tip in advice)
        )

    def test_good_conditions_advice_when_nothing_is_risky(self):
        advice = _build_advice(self._current(), [self._day()])

        self.assertEqual(len(advice), 1)
        self.assertEqual(advice[0]['tone'], 'success')


class WeatherWidgetViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='weather-viewer',
            password='secret1234',
        )
        self.farm = Farm.objects.create(
            user=self.user,
            name='Green Valley Farm',
            owner='Mia Santos',
            location='Davao City',
            size_hectares=Decimal('12.50'),
            date_registered=timezone.now(),
        )
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_weather_widget_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse('weather_widget'))

        self.assertEqual(response.status_code, 302)

    @patch('apps.core.weather._request_json')
    def test_weather_widget_renders_the_forecast(self, request_json):
        request_json.side_effect = _request_side_effect

        response = self.client.get(reverse('weather_widget'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Davao City')
        self.assertContains(response, 'Green Valley Farm')
        self.assertContains(response, 'Open-Meteo')
        self.assertContains(response, '32')
        self.assertEqual(
            response['Cache-Control'],
            'private, no-store',
        )

    @patch(
        'apps.core.weather._request_json',
        side_effect=URLError('offline'),
    )
    def test_weather_widget_renders_unavailable_state(self, request_json):
        response = self.client.get(reverse('weather_widget'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Local weather is unavailable')
        self.assertContains(response, 'data-weather-retry')

    def test_dashboard_contains_the_weather_container(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dashboardWeather"')
        self.assertContains(response, reverse('weather_widget'))
