from typing import Dict, Any, List
from datetime import datetime
from backend.tools.registry import registry


@registry.register(
    name="budget_check",
    description="Validate if an option's total fare is strictly within the user's maximum authorized budget limit."
)
def budget_check(fare: float, max_budget: float) -> Dict[str, Any]:
    is_valid = float(fare) <= float(max_budget)
    difference = round(float(max_budget) - float(fare), 2)
    return {
        "is_within_budget": is_valid,
        "fare": round(float(fare), 2),
        "max_budget": round(float(max_budget), 2),
        "remaining_budget": difference,
        "rejection_reason": None if is_valid else f"Fare ${fare:.2f} exceeds max budget ${max_budget:.2f} by ${abs(difference):.2f}"
    }


@registry.register(
    name="deadline_check",
    description="Validate if an option's estimated arrival time strictly satisfies the desired arrival deadline."
)
def deadline_check(estimated_arrival: str, deadline_time: str) -> Dict[str, Any]:
    try:
        arr_dt = datetime.strptime(estimated_arrival, "%H:%M")
        dl_dt = datetime.strptime(deadline_time, "%H:%M")
        is_on_time = arr_dt <= dl_dt
        diff_minutes = int((dl_dt - arr_dt).total_seconds() / 60)
        return {
            "is_on_time": is_on_time,
            "estimated_arrival": estimated_arrival,
            "deadline_time": deadline_time,
            "buffer_minutes": diff_minutes,
            "rejection_reason": None if is_on_time else f"Arrival time {estimated_arrival} arrives {abs(diff_minutes)} min past deadline {deadline_time}"
        }
    except Exception as e:
        return {"error": str(e), "is_on_time": True, "buffer_minutes": 0}


@registry.register(
    name="booking_eligibility",
    description="Check whether an option requires seat reservation, has seats available, and satisfies auto-booking authorization constraints."
)
def booking_eligibility(
    requires_booking: bool,
    available_seats: int,
    total_fare: float,
    max_auto_budget: float = 50.0,
    user_authorized: bool = False
) -> Dict[str, Any]:
    if not requires_booking:
        return {
            "requires_booking": False,
            "is_eligible_for_auto_booking": False,
            "can_board_directly": True,
            "reason": "Direct boarding transit mode (e.g. Metro/Bus) does not require seat reservation."
        }

    has_seats = available_seats > 0
    within_auto_budget = total_fare <= max_auto_budget
    is_eligible = has_seats and within_auto_budget and user_authorized

    reasons = []
    if not has_seats:
        reasons.append("No seats available.")
    if not within_auto_budget:
        reasons.append(f"Fare ${total_fare:.2f} exceeds auto-booking cap ${max_auto_budget:.2f}.")
    if not user_authorized:
        reasons.append("Explicit auto-booking authorization not granted by user.")

    return {
        "requires_booking": True,
        "is_eligible_for_auto_booking": is_eligible,
        "available_seats": available_seats,
        "within_auto_budget": within_auto_budget,
        "user_authorized": user_authorized,
        "reasons": reasons
    }
