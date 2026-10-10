from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from backend.schemas import CommuteOption, SeatItem, BookingRecord


class TransitProvider(ABC):
    @abstractmethod
    def search_routes(self, origin: str, destination: str, target_arrival: str, journey_date: str) -> List[CommuteOption]:
        pass


class WeatherTrafficProvider(ABC):
    @abstractmethod
    def get_weather(self, location: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_traffic_status(self, origin: str, destination: str) -> Dict[str, Any]:
        pass


class BookingProvider(ABC):
    @abstractmethod
    def check_seat_availability(self, option_id: str, journey_date: str) -> List[SeatItem]:
        pass

    @abstractmethod
    def execute_booking(self, request_data: Dict[str, Any]) -> BookingRecord:
        pass

    @abstractmethod
    def verify_booking(self, booking_id: str) -> Dict[str, Any]:
        pass
