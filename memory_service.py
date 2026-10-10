from typing import Dict, Any, List, Optional
from datetime import datetime
from backend.database import (
    save_user_preferences,
    get_user_preferences,
    save_session_state,
    get_session_state,
    get_tool_logs,
    save_booking,
    get_booking_by_id,
    get_all_bookings,
    get_booking_by_idempotency_key
)


class MemoryService:
    """
    SQLite-backed memory and task recovery service.
    Guarantees state persistence across server restarts and crashes.
    """
    def get_preferences(self, user_id: str = "default_user") -> Dict[str, Any]:
        return get_user_preferences(user_id)

    def update_preferences(self, prefs: Dict[str, Any]):
        save_user_preferences(prefs)

    def save_agent_session(self, session_id: str, status: str, request_data: Dict[str, Any], plan_response: Dict[str, Any], option_id: Optional[str] = None):
        save_session_state(session_id, status, request_data, plan_response, option_id)

    def recover_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return get_session_state(session_id)

    def get_recent_traces(self, session_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return get_tool_logs(session_id, limit=limit)

    def save_booking_record(self, record_dict: Dict[str, Any]):
        save_booking(record_dict)

    def get_booking(self, booking_id: str) -> Optional[Dict[str, Any]]:
        return get_booking_by_id(booking_id)

    def get_booking_by_idempotency(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        return get_booking_by_idempotency_key(idempotency_key)

    def list_all_bookings(self, limit: int = 50) -> List[Dict[str, Any]]:
        return get_all_bookings(limit=limit)


memory_service = MemoryService()
