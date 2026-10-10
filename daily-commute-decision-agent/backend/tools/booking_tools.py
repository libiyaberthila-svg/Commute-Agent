from typing import List, Dict, Any, Optional
from backend.tools.registry import registry
from backend.providers.mock_booking import MockBookingProvider
from backend.database import get_booking_by_id, get_booking_by_idempotency_key, get_all_bookings

booking_provider = MockBookingProvider()


@registry.register(
    name="seat_availability",
    description="Retrieve live seat map, coach details, and availability for a specific transit option."
)
def seat_availability(option_id: str, journey_date: str = "") -> List[Dict[str, Any]]:
    seats = booking_provider.check_seat_availability(option_id, journey_date)
    return [s.model_dump() for s in seats]


@registry.register(
    name="seat_selection",
    description="Select the best available seat matching user preference (e.g. window, aisle, quiet, front)."
)
def seat_selection(option_id: str, preference: str = "window") -> Dict[str, Any]:
    seat = booking_provider.select_best_seat(option_id, preference)
    if seat:
        return {
            "selected": True,
            "seat": seat.model_dump(),
            "preference": preference,
            "status": "SEAT_MATCHED"
        }
    return {
        "selected": False,
        "seat": None,
        "preference": preference,
        "status": "NO_SEAT_AVAILABLE"
    }


@registry.register(
    name="booking_execution",
    description="Execute seat reservation with strict idempotency, budget limits, authorization checks, and verification."
)
def booking_execution(
    option_id: str,
    journey_date: str,
    passenger_name: str = "Commuter",
    passenger_count: int = 1,
    seat_number: Optional[str] = None,
    seat_preference: str = "window",
    max_budget: float = 50.0,
    total_fare: float = 12.50,
    origin: str = "North Station",
    destination: str = "Financial District",
    departure_time: str = "08:25",
    arrival_time: str = "09:00",
    is_auto_booked: bool = False,
    user_authorized: bool = True,
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    req = {
        "option_id": option_id,
        "journey_date": journey_date,
        "passenger_name": passenger_name,
        "passenger_count": passenger_count,
        "seat_number": seat_number,
        "seat_preference": seat_preference,
        "max_budget": max_budget,
        "total_fare": total_fare,
        "origin": origin,
        "destination": destination,
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "is_auto_booked": is_auto_booked,
        "user_authorized": user_authorized,
        "idempotency_key": idempotency_key
    }
    record = booking_provider.execute_booking(req)
    return record.model_dump()


@registry.register(
    name="booking_verification",
    description="Verify a booking with the provider using booking ID and verification code."
)
def booking_verification(booking_id: str) -> Dict[str, Any]:
    return booking_provider.verify_booking(booking_id)


@registry.register(
    name="booking_status",
    description="Check real-time status and confirmation details of an existing booking."
)
def booking_status(booking_id: str) -> Dict[str, Any]:
    rec = get_booking_by_id(booking_id)
    if not rec:
        return {"status": "NOT_FOUND", "booking_id": booking_id, "found": False}
    return {"status": rec["status"], "booking": rec, "found": True}


@registry.register(
    name="booking_recovery",
    description="Safely recover booking state or check idempotency status after a system disruption or timeout."
)
def booking_recovery(idempotency_key: str) -> Dict[str, Any]:
    rec = get_booking_by_idempotency_key(idempotency_key)
    if rec:
        return {
            "recovered": True,
            "status": rec["status"],
            "booking": rec,
            "message": "Existing confirmed booking recovered without duplicate payment."
        }
    return {
        "recovered": False,
        "status": "NO_PREVIOUS_RECORD",
        "message": "No existing transaction found for this idempotency key. Safe to initiate."
    }
