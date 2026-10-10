from typing import List
from datetime import datetime, timedelta
from backend.providers.base import TransitProvider
from backend.schemas import CommuteOption, RouteSegment
from backend.config import settings


class MockTransitProvider(TransitProvider):
    """
    Mock Transit Provider supplying realistic commute routes for cities.
    Clearly labeled as Mock Data Provider (no real API costs or keys).
    """
    def __init__(self):
        self.provider_id = "mock_transit_adapter"
        self.is_live = False

    def _calculate_times(self, target_arrival: str, duration_min: int) -> tuple[str, str]:
        try:
            arr_dt = datetime.strptime(target_arrival, "%H:%M")
        except Exception:
            arr_dt = datetime.strptime("09:00", "%H:%M")
        dep_dt = arr_dt - timedelta(minutes=duration_min)
        return dep_dt.strftime("%H:%M"), arr_dt.strftime("%H:%M")

    def search_routes(self, origin: str, destination: str, target_arrival: str, journey_date: str) -> List[CommuteOption]:
        # Generate 4 distinct realistic commuting options with INR fares
        options = []

        # 1. Express Rail / Commuter Train (Requires Seat Reservation)
        dep_train, arr_train = self._calculate_times(target_arrival, 35)
        options.append(CommuteOption(
            id="opt_train_exp_101",
            mode="express_train",
            title=f"Express Rail Line 9 ({origin} -> {destination})",
            origin=origin,
            destination=destination,
            departure_time=dep_train,
            arrival_time=arr_train,
            duration_minutes=35,
            base_fare=180.0,
            total_fare=180.0,
            currency="INR",
            reliability_score=0.96,
            weather_impact="All-weather shielded track",
            traffic_delay_min=0,
            available_seats=18,
            requires_booking=True,
            provider_id=self.provider_id,
            is_live_provider=False,
            segments=[
                RouteSegment(
                    mode="express_train",
                    from_stop=origin,
                    to_stop=destination,
                    duration_min=35,
                    fare=180.0,
                    line_name="Express Line 9",
                    departure_time=dep_train,
                    arrival_time=arr_train
                )
            ]
        ))

        # 2. Metro Rapid Transit (No booking, fixed fare)
        dep_metro, arr_metro = self._calculate_times(target_arrival, 45)
        options.append(CommuteOption(
            id="opt_metro_blue_204",
            mode="metro",
            title=f"Metro Blue Line Subway ({origin} -> {destination})",
            origin=origin,
            destination=destination,
            departure_time=dep_metro,
            arrival_time=arr_metro,
            duration_minutes=45,
            base_fare=35.0,
            total_fare=35.0,
            currency="INR",
            reliability_score=0.92,
            weather_impact="Underground unaffected by surface rain",
            traffic_delay_min=0,
            available_seats=120,
            requires_booking=False,
            provider_id=self.provider_id,
            is_live_provider=False,
            segments=[
                RouteSegment(
                    mode="metro",
                    from_stop=origin,
                    to_stop=destination,
                    duration_min=45,
                    fare=35.0,
                    line_name="Blue Line Direct",
                    departure_time=dep_metro,
                    arrival_time=arr_metro
                )
            ]
        ))

        # 3. City Express Bus (Budget friendly, road dependent)
        dep_bus, arr_bus = self._calculate_times(target_arrival, 55)
        options.append(CommuteOption(
            id="opt_bus_exp_305",
            mode="bus",
            title=f"Rapid Transit Bus 44X ({origin} -> {destination})",
            origin=origin,
            destination=destination,
            departure_time=dep_bus,
            arrival_time=arr_bus,
            duration_minutes=55,
            base_fare=25.0,
            total_fare=25.0,
            currency="INR",
            reliability_score=0.82,
            weather_impact="Subject to wet road braking distances",
            traffic_delay_min=5,
            available_seats=24,
            requires_booking=False,
            provider_id=self.provider_id,
            is_live_provider=False,
            segments=[
                RouteSegment(
                    mode="bus",
                    from_stop=origin,
                    to_stop=destination,
                    duration_min=55,
                    fare=25.0,
                    line_name="Express Bus 44X",
                    departure_time=dep_bus,
                    arrival_time=arr_bus
                )
            ]
        ))

        # 4. On-Demand RideShare / Express Shuttle (Door-to-door, fastest off-peak, premium fare)
        dep_ride, arr_ride = self._calculate_times(target_arrival, 28)
        options.append(CommuteOption(
            id="opt_rideshare_prime_402",
            mode="rideshare",
            title=f"Direct Premium Rideshare ({origin} -> {destination})",
            origin=origin,
            destination=destination,
            departure_time=dep_ride,
            arrival_time=arr_ride,
            duration_minutes=28,
            base_fare=450.0,
            total_fare=450.0,
            currency="INR",
            reliability_score=0.88,
            weather_impact="Moderate rain caution",
            traffic_delay_min=4,
            available_seats=4,
            requires_booking=True,
            provider_id=self.provider_id,
            is_live_provider=False,
            segments=[
                RouteSegment(
                    mode="rideshare",
                    from_stop=origin,
                    to_stop=destination,
                    duration_min=28,
                    fare=450.0,
                    line_name="Express Carpool",
                    departure_time=dep_ride,
                    arrival_time=arr_ride
                )
            ]
        ))

        return options
