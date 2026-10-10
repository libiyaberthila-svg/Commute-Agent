from typing import Dict, Any
from backend.providers.base import WeatherTrafficProvider


class MockWeatherTrafficProvider(WeatherTrafficProvider):
    """
    Mock Weather & Traffic Provider. Supports dynamic simulation overrides.
    """
    def __init__(self):
        self.weather_override = None
        self.traffic_override = None

    def set_simulation(self, weather_override: Dict[str, Any] = None, traffic_override: Dict[str, Any] = None):
        self.weather_override = weather_override
        self.traffic_override = traffic_override

    def reset_simulation(self):
        self.weather_override = None
        self.traffic_override = None

    def get_weather(self, location: str) -> Dict[str, Any]:
        if self.weather_override:
            return self.weather_override

        return {
            "location": location,
            "condition": "Partly Cloudy",
            "temperature_c": 21.5,
            "precipitation_chance": 10,
            "wind_speed_kmh": 12,
            "advisory": "Clear conditions for all transit modes",
            "is_mock": True
        }

    def get_traffic_status(self, origin: str, destination: str) -> Dict[str, Any]:
        if self.traffic_override:
            return self.traffic_override

        return {
            "origin": origin,
            "destination": destination,
            "congestion_level": "Moderate",  # Low, Moderate, Heavy, Severe
            "average_speed_kmh": 42,
            "delay_minutes": 5,
            "incidents": [],
            "road_condition": "Dry",
            "is_mock": True
        }
