from typing import Dict, Any, List, Optional
from backend.tools.registry import registry
from backend.database import get_user_preferences, save_user_preferences, get_all_bookings


@registry.register(
    name="user_preferences",
    description="Retrieve or update stored user preferences including max budget, preferred transit modes, and seat preferences."
)
def user_preferences(user_id: str = "default_user", update_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if update_data:
        update_data["user_id"] = user_id
        save_user_preferences(update_data)
    return get_user_preferences(user_id)


@registry.register(
    name="commute_history",
    description="Retrieve historical commute decisions, recent bookings, and reliability track records."
)
def commute_history(limit: int = 10) -> List[Dict[str, Any]]:
    bookings = get_all_bookings(limit=limit)
    return bookings
