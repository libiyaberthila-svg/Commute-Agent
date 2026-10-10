from typing import Dict, Any, Optional, List
from backend.tools.registry import registry
from backend.database import (
    get_demo_user,
    get_wallet,
    topup_wallet,
    process_wallet_payment,
    get_wallet_transactions,
    get_booking_by_id
)
from backend.providers.mock_booking import MockBookingProvider

booking_provider = MockBookingProvider()


@registry.register(
    name="demo_account_tool",
    description="Retrieve demo commuter user profile, authentication status, and linked wallet summary."
)
def demo_account_tool(username: str = "demo_commuter") -> Dict[str, Any]:
    user = get_demo_user(username)
    if not user:
        return {"found": False, "error": f"Demo user '{username}' not found."}
    wallet = get_wallet(username)
    return {
        "found": True,
        "username": user["username"],
        "display_name": user["display_name"],
        "email": user["email"],
        "role": user["role"],
        "wallet_balance": wallet["balance"],
        "currency": wallet["currency"],
        "is_simulated": True
    }


@registry.register(
    name="wallet_balance_tool",
    description="Check the current simulated demo wallet balance and currency for a user."
)
def wallet_balance_tool(user_id: str = "demo_commuter") -> Dict[str, Any]:
    wallet = get_wallet(user_id)
    return {
        "user_id": user_id,
        "balance": wallet["balance"],
        "currency": wallet["currency"],
        "is_simulated": True,
        "updated_at": wallet.get("updated_at")
    }


@registry.register(
    name="wallet_topup_tool",
    description="Add simulated demo funds to the user's wallet with SQLite persistence and transaction auditing."
)
def wallet_topup_tool(user_id: str = "demo_commuter", amount: float = 500.0, description: str = "Simulated Wallet Top-up") -> Dict[str, Any]:
    try:
        res = topup_wallet(user_id=user_id, amount=amount, description=description)
        return res
    except Exception as e:
        return {"success": False, "error": str(e)}


@registry.register(
    name="seat_availability_tool",
    description="Retrieve live coach seat layout, seat numbers, types (window/aisle/quiet/front) and availability."
)
def seat_availability_tool(option_id: str = "opt_train_exp_101", journey_date: str = "") -> List[Dict[str, Any]]:
    seats = booking_provider.check_seat_availability(option_id, journey_date)
    return [s.model_dump() for s in seats]


@registry.register(
    name="seat_selection_tool",
    description="Select and lock the best matching seat for a given user preference (window, aisle, quiet, front)."
)
def seat_selection_tool(option_id: str = "opt_train_exp_101", preference: str = "window") -> Dict[str, Any]:
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
    name="fare_validation_tool",
    description="Validate base fare, seat surcharge, passenger count, and verify total amount against wallet balance or budget."
)
def fare_validation_tool(
    base_fare: float,
    seat_fee: float = 0.0,
    passenger_count: int = 1,
    user_id: str = "demo_commuter",
    payment_mode: str = "ONLINE_WALLET"
) -> Dict[str, Any]:
    total_fare = (base_fare + seat_fee) * passenger_count
    wallet = get_wallet(user_id)
    has_sufficient_balance = wallet["balance"] >= total_fare if payment_mode == "ONLINE_WALLET" else True

    return {
        "base_fare": base_fare,
        "seat_fee": seat_fee,
        "passenger_count": passenger_count,
        "total_fare": round(total_fare, 2),
        "currency": "INR",
        "payment_mode": payment_mode,
        "wallet_balance": wallet["balance"],
        "has_sufficient_balance": has_sufficient_balance,
        "is_valid": True if (payment_mode == "OFFLINE_PAY_LATER" or has_sufficient_balance) else False,
        "rejection_reason": None if (payment_mode == "OFFLINE_PAY_LATER" or has_sufficient_balance) else f"Insufficient wallet balance: ₹{wallet['balance']:.2f} available, ₹{total_fare:.2f} required."
    }


@registry.register(
    name="payment_method_tool",
    description="Validate and select payment method (ONLINE_WALLET or OFFLINE_PAY_LATER) and configure transaction rules."
)
def payment_method_tool(requested_mode: str = "ONLINE_WALLET", user_id: str = "demo_commuter") -> Dict[str, Any]:
    mode = requested_mode.upper()
    if mode not in ("ONLINE_WALLET", "OFFLINE_PAY_LATER"):
        mode = "ONLINE_WALLET"
    
    wallet = get_wallet(user_id)
    return {
        "selected_mode": mode,
        "is_online_wallet": mode == "ONLINE_WALLET",
        "is_offline_pay_later": mode == "OFFLINE_PAY_LATER",
        "wallet_available_balance": wallet["balance"],
        "currency": wallet["currency"],
        "rules": "ONLINE_WALLET deducts immediately on confirmed booking. OFFLINE_PAY_LATER preserves reservation with PENDING_PAYMENT status."
    }


@registry.register(
    name="demo_wallet_payment_tool",
    description="Process atomic payment debit from the simulated demo wallet for a confirmed booking."
)
def demo_wallet_payment_tool(
    user_id: str = "demo_commuter",
    amount: float = 180.0,
    booking_id: str = "MOCK-BKG-001",
    description: str = "Seat Reservation Payment",
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    return process_wallet_payment(
        user_id=user_id,
        amount=amount,
        booking_id=booking_id,
        description=description,
        idempotency_key=idempotency_key
    )


@registry.register(
    name="offline_payment_tool",
    description="Register an offline pay-later order with outstanding balance tracking and PENDING_PAYMENT status."
)
def offline_payment_tool(
    booking_id: str,
    amount: float,
    passenger_name: str = "Demo Commuter",
    due_date: Optional[str] = None
) -> Dict[str, Any]:
    return {
        "payment_mode": "OFFLINE_PAY_LATER",
        "booking_id": booking_id,
        "amount_due": amount,
        "currency": "INR",
        "passenger_name": passenger_name,
        "payment_status": "PENDING_PAYMENT",
        "message": f"Offline Pay Later recorded. Outstanding amount of ₹{amount:.2f} due at transit boarding counter."
    }


@registry.register(
    name="transaction_verification_tool",
    description="Verify transaction details, debit status, and audit log from SQLite wallet transactions."
)
def transaction_verification_tool(txn_id: str, user_id: str = "demo_commuter") -> Dict[str, Any]:
    txns = get_wallet_transactions(user_id=user_id, limit=100)
    matched = [t for t in txns if t["txn_id"] == txn_id]
    if matched:
        return {
            "found": True,
            "transaction": matched[0],
            "verified": matched[0]["status"] == "SUCCESS"
        }
    return {
        "found": False,
        "verified": False,
        "error": f"Transaction ID '{txn_id}' not found in ledger."
    }


@registry.register(
    name="booking_verification_tool",
    description="Verify booking reservation, seat status, provider confirmation, and attached receipt."
)
def booking_verification_tool(booking_id: str) -> Dict[str, Any]:
    return booking_provider.verify_booking(booking_id)


@registry.register(
    name="payment_reconciliation_tool",
    description="Reconcile uncertain payment timeouts or network disconnects before retrying to prevent duplicate charges."
)
def payment_reconciliation_tool(booking_id: str, idempotency_key: Optional[str] = None, user_id: str = "demo_commuter") -> Dict[str, Any]:
    booking = get_booking_by_id(booking_id)
    txns = get_wallet_transactions(user_id=user_id, limit=50)
    matching_txn = [t for t in txns if t.get("booking_id") == booking_id or (idempotency_key and t.get("idempotency_key") == f"pay_{idempotency_key}")]

    if booking and matching_txn:
        return {
            "reconciled": True,
            "status": "PAID_AND_CONFIRMED",
            "booking_id": booking_id,
            "txn_id": matching_txn[0]["txn_id"],
            "amount": matching_txn[0]["amount"],
            "action": "Do not charge again. Existing confirmed booking is valid."
        }
    elif booking and booking.get("payment_mode") == "OFFLINE_PAY_LATER":
        return {
            "reconciled": True,
            "status": "OFFLINE_PENDING",
            "booking_id": booking_id,
            "action": "Booking confirmed with pay-later status."
        }
    elif not booking and not matching_txn:
        return {
            "reconciled": True,
            "status": "CLEAN_TO_PROCESS",
            "action": "No prior transaction or booking exists. Safe to process new booking."
        }
    else:
        return {
            "reconciled": True,
            "status": "REQUIRES_REVIEW",
            "action": "Discrepancy detected between booking and payment ledger."
        }
