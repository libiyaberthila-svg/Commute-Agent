import pytest
import uuid
from backend.database import init_db
from backend.providers.mock_booking import MockBookingProvider
from backend.schemas import BookingExecutionRequest





def test_booking_successful_flow():
    provider = MockBookingProvider()
    req = {
        "option_id": "opt_train_exp_101",
        "journey_date": "2026-10-10",
        "passenger_name": "Alice Commuter",
        "passenger_count": 1,
        "seat_preference": "window",
        "max_budget": 500.0,
        "total_fare": 180.0,
        "origin": "North Station",
        "destination": "Financial District",
        "user_authorized": True,
        "is_auto_booked": True,
        "idempotency_key": f"test_idem_{uuid.uuid4().hex[:6]}"
    }

    record = provider.execute_booking(req)
    assert record.status == "CONFIRMED"
    assert record.is_mock is True
    assert record.verification_code is not None
    assert record.seat_number is not None

    # Verify booking
    verif = provider.verify_booking(record.booking_id)
    assert verif["verified"] is True
    assert verif["booking_id"] == record.booking_id


def test_booking_unauthorized_rejection():
    provider = MockBookingProvider()
    req = {
        "option_id": "opt_train_exp_101",
        "journey_date": "2026-10-10",
        "passenger_name": "Bob",
        "user_authorized": False,  # Hard constraint: Unauthorized
        "max_budget": 500.0,
        "total_fare": 180.0
    }
    record = provider.execute_booking(req)
    assert record.status == "FAILED"
    assert "Unauthorized" in record.failure_reason


def test_booking_budget_limit_rejection():
    provider = MockBookingProvider()
    req = {
        "option_id": "opt_train_exp_101",
        "journey_date": "2026-10-10",
        "passenger_name": "Charlie",
        "user_authorized": True,
        "max_budget": 100.00,  # Fare is 180.0, budget is 100.0
        "total_fare": 180.0
    }
    record = provider.execute_booking(req)
    assert record.status == "FAILED"
    assert "exceeds" in record.failure_reason


def test_booking_idempotency_and_duplicate_prevention():
    provider = MockBookingProvider()
    idem_key = f"idem_dup_check_{uuid.uuid4().hex[:8]}"

    req = {
        "option_id": "opt_train_exp_101",
        "journey_date": "2026-10-10",
        "passenger_name": "Dana",
        "user_authorized": True,
        "max_budget": 500.0,
        "total_fare": 180.0,
        "idempotency_key": idem_key
    }

    # First booking
    first_record = provider.execute_booking(req)
    assert first_record.status == "CONFIRMED"

    # Second booking with same idempotency key (simulating retry or double click)
    second_record = provider.execute_booking(req)
    assert second_record.status == "CONFIRMED"
    assert second_record.booking_id == first_record.booking_id
    assert second_record.seat_number == first_record.seat_number
    assert second_record.verification_code == first_record.verification_code
