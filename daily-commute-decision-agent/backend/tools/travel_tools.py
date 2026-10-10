from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from backend.tools.registry import registry
from backend.providers.mock_transit import MockTransitProvider
from backend.providers.mock_weather import MockWeatherTrafficProvider
from backend.schemas import CommuteOption

transit_provider = MockTransitProvider()
weather_provider = MockWeatherTrafficProvider()


@registry.register(
    name="route_search",
    description="Search for available transit and commute routes between origin and destination for a target arrival time."
)
def route_search(origin: str, destination: str, target_arrival: str = "09:00", journey_date: str = "") -> List[Dict[str, Any]]:
    routes = transit_provider.search_routes(origin, destination, target_arrival, journey_date)
    return [r.model_dump() for r in routes]


@registry.register(
    name="weather",
    description="Retrieve live weather conditions, precipitation chance, and transit advisories for a location."
)
def weather(location: str) -> Dict[str, Any]:
    return weather_provider.get_weather(location)


@registry.register(
    name="traffic_status",
    description="Get current traffic congestion level, estimated road delay in minutes, and incidents."
)
def traffic_status(origin: str, destination: str) -> Dict[str, Any]:
    return weather_provider.get_traffic_status(origin, destination)


@registry.register(
    name="transport_search",
    description="Search specific transit transport services matching a requested mode (e.g. metro, bus, express_train, rideshare)."
)
def transport_search(origin: str, destination: str, mode: str = "metro", target_arrival: str = "09:00") -> List[Dict[str, Any]]:
    all_routes = transit_provider.search_routes(origin, destination, target_arrival, "")
    filtered = [r.model_dump() for r in all_routes if r.mode.lower() == mode.lower()]
    return filtered


@registry.register(
    name="travel_time",
    description="Calculate exact duration in minutes and ETA based on mode, distance, and real-time traffic delay."
)
def travel_time(origin: str, destination: str, mode: str = "metro", departure_time: str = "08:15") -> Dict[str, Any]:
    # Mode base durations
    base_durations = {
        "rideshare": 28,
        "express_train": 35,
        "metro": 45,
        "bus": 55,
        "bike": 60,
        "walking": 120
    }
    base = base_durations.get(mode.lower(), 45)
    traffic = weather_provider.get_traffic_status(origin, destination)
    delay = traffic.get("delay_minutes", 0) if mode.lower() in ("bus", "rideshare") else 0
    total_min = base + delay

    try:
        dep_dt = datetime.strptime(departure_time, "%H:%M")
        arr_dt = dep_dt + timedelta(minutes=total_min)
        eta = arr_dt.strftime("%H:%M")
    except Exception:
        eta = "09:00"

    return {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "base_duration_min": base,
        "traffic_delay_min": delay,
        "total_duration_min": total_min,
        "departure_time": departure_time,
        "estimated_arrival_time": eta
    }


@registry.register(
    name="fare_comparison",
    description="Compare monetary fares, pass eligibility, and surge multipliers across all available transit options."
)
def fare_comparison(origin: str, destination: str, target_arrival: str = "09:00") -> List[Dict[str, Any]]:
    routes = transit_provider.search_routes(origin, destination, target_arrival, "")
    comparison = []
    for r in routes:
        comparison.append({
            "id": r.id,
            "mode": r.mode,
            "title": r.title,
            "base_fare": r.base_fare,
            "total_fare": r.total_fare,
            "requires_booking": r.requires_booking,
            "reliability_score": r.reliability_score
        })
    comparison.sort(key=lambda x: x["total_fare"])
    return comparison


@registry.register(
    name="departure_time",
    description="Calculate the required departure time to arrive at the destination before a strict deadline."
)
def departure_time(destination: str, target_arrival: str = "09:00", duration_minutes: int = 40, buffer_minutes: int = 10) -> Dict[str, Any]:
    try:
        arr_dt = datetime.strptime(target_arrival, "%H:%M")
        total_sub = duration_minutes + buffer_minutes
        dep_dt = arr_dt - timedelta(minutes=total_sub)
        return {
            "target_arrival": target_arrival,
            "duration_minutes": duration_minutes,
            "buffer_minutes": buffer_minutes,
            "recommended_departure_time": dep_dt.strftime("%H:%M"),
            "safety_buffer_included": True
        }
    except Exception as e:
        return {"error": str(e), "recommended_departure_time": "08:10"}


@registry.register(
    name="alternative_route",
    description="Find backup alternative routes avoiding a specific disrupted mode or transit corridor."
)
def alternative_route(origin: str, destination: str, avoid_mode: str, target_arrival: str = "09:00") -> List[Dict[str, Any]]:
    all_routes = transit_provider.search_routes(origin, destination, target_arrival, "")
    filtered = [r.model_dump() for r in all_routes if r.mode.lower() != avoid_mode.lower()]
    return filtered
