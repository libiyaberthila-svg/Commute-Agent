import pytest
import uuid
from backend.database import (
    init_db,
    authenticate_user,
    get_demo_user,
    get_wallet,
    topup_wallet,
    process_wallet_payment,
    get_wallet_transactions
)
from backend.providers.mock_booking import MockBookingProvider
from backend.tools.registry import registry
import backend.tools.wallet_and_payment_tools





def test_demo_account_and_initial_balance():
    # Authenticate default demo user
    user = authenticate_user("demo_commuter", "demo123")
    assert user is not None
    assert user["username"] == "demo_commuter"

    # Verify initial ₹5000 wallet
    wallet = get_wallet("demo_commuter")
    assert wallet["balance"] > 0
    assert wallet["currency"] == "INR"
    assert wallet["is_simulated"] is True


def test_wallet_topup():
    initial_wallet = get_wallet("demo_commuter")
    init_bal = initial_wallet["balance"]

    res = topup_wallet("demo_commuter", 500.0, "Test Top-up")
    assert res["success"] is True
    assert res["new_balance"] == init_bal + 500.0

    # Check transaction log
    txns = get_wallet_transactions("demo_commuter", limit=5)
    assert any(t["txn_type"] == "CREDIT" and t["amount"] == 500.0 for t in txns)


def test_online_wallet_payment_sufficient_balance():
    provider = MockBookingProvider()
    user_id = f"test_user_{uuid.uuid4().hex[:6]}"
    # Initialize test wallet with ₹1000
    topup_wallet(user_id, 1000.0, "Seed test")

    req = {
        "option_id": "opt_train_exp_101",
        "journey_date": "2026-10-10",
        "user_id": user_id,
        "passenger_name": "Test Commuter",
        "passenger_count": 1,
        "seat_preference": "window",
        "max_budget": 500.0,
        "total_fare": 180.0,
        "origin": "Station A",
        "destination": "Station B",
        "payment_mode": "ONLINE_WALLET",
        "user_authorized": True,
        "is_auto_booked": True,
        "idempotency_key": f"pay_test_{uuid.uuid4().hex[:6]}"
    }

    record = provider.execute_booking(req)
    assert record.status == "CONFIRMED"
    assert record.payment_mode == "ONLINE_WALLET"
    assert record.payment_status == "PAID"
    assert record.receipt is not None
    assert record.receipt.total_paid == 180.0

    # Verify wallet was debited
    wallet = get_wallet(user_id)
    assert wallet["balance"] == 1000.0 - 180.0


def test_online_wallet_payment_insufficient_balance_zero_deduction():
    provider = MockBookingProvider()
    poor_user = f"poor_user_{uuid.uuid4().hex[:6]}"
    # Seed with only ₹50
    topup_wallet(poor_user, 50.0, "Small seed")

    req = {
        "option_id": "opt_train_exp_101",
        "journey_date": "2026-10-10",
        "user_id": poor_user,
        "passenger_name": "Poor Commuter",
        "passenger_count": 1,
        "seat_preference": "window",
        "max_budget": 500.0,
        "total_fare": 180.0,  # Costs 180, wallet only has 50
        "payment_mode": "ONLINE_WALLET",
        "user_authorized": True
    }

    record = provider.execute_booking(req)
    assert record.status == "FAILED"
    assert "Insufficient wallet balance" in record.failure_reason

    # Balance must remain exactly 50 (ZERO DEDUCTION)
    wallet = get_wallet(poor_user)
    assert wallet["balance"] == 50.0


def test_offline_pay_later_flow():
    provider = MockBookingProvider()
    offline_user = f"offline_user_{uuid.uuid4().hex[:6]}"
    topup_wallet(offline_user, 500.0, "Seed")

    req = {
        "option_id": "opt_train_exp_101",
        "journey_date": "2026-10-10",
        "user_id": offline_user,
        "passenger_name": "Offline Commuter",
        "passenger_count": 1,
        "seat_preference": "window",
        "max_budget": 500.0,
        "total_fare": 180.0,
        "payment_mode": "OFFLINE_PAY_LATER",
        "user_authorized": True,
        "is_auto_booked": True
    }

    record = provider.execute_booking(req)
    assert record.status == "CONFIRMED"
    assert record.payment_mode == "OFFLINE_PAY_LATER"
    assert record.payment_status == "PENDING_PAYMENT"

    # Wallet balance must NOT be deducted
    wallet = get_wallet(offline_user)
    assert wallet["balance"] == 500.0


def test_duplicate_payment_prevention_idempotency():
    provider = MockBookingProvider()
    user_id = f"idem_user_{uuid.uuid4().hex[:6]}"
    topup_wallet(user_id, 1000.0, "Seed")
    idem_key = f"unique_order_{uuid.uuid4().hex[:8]}"

    req = {
        "option_id": "opt_train_exp_101",
        "journey_date": "2026-10-10",
        "user_id": user_id,
        "passenger_name": "Idem Commuter",
        "passenger_count": 1,
        "max_budget": 500.0,
        "total_fare": 180.0,
        "payment_mode": "ONLINE_WALLET",
        "user_authorized": True,
        "idempotency_key": idem_key
    }

    # First attempt
    rec1 = provider.execute_booking(req)
    assert rec1.status == "CONFIRMED"
    assert get_wallet(user_id)["balance"] == 820.0

    # Second attempt with same idempotency key (simulating retry)
    rec2 = provider.execute_booking(req)
    assert rec2.status == "CONFIRMED"
    assert rec2.booking_id == rec1.booking_id

    # Balance must STILL be 820.0 (no double deduction)
    assert get_wallet(user_id)["balance"] == 820.0


def test_new_wallet_and_payment_tools_registered():
    tool_names = [t["name"] for t in registry.list_tools()]
    expected_new = [
        "demo_account_tool",
        "wallet_balance_tool",
        "wallet_topup_tool",
        "seat_availability_tool",
        "seat_selection_tool",
        "fare_validation_tool",
        "payment_method_tool",
        "demo_wallet_payment_tool",
        "offline_payment_tool",
        "transaction_verification_tool",
        "booking_verification_tool",
        "payment_reconciliation_tool"
    ]
    for exp in expected_new:
        assert exp in tool_names, f"Expected tool {exp} to be registered"
