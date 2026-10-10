import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.providers.base import BookingProvider
from backend.schemas import SeatItem, BookingRecord, BookingReceipt
from backend.database import (
    get_booking_by_idempotency_key,
    get_booking_by_id,
    save_booking,
    process_wallet_payment,
    get_wallet
)
from backend.config import settings


class MockBookingProvider(BookingProvider):
    """
    Testable Mock Booking Provider with real booking & payment lifecycle:
    - Seat selection & live layout
    - Online Demo Wallet vs. Offline Pay Later
    - Atomic wallet deduction & zero-deduction failure handling
    - Idempotency & duplicate booking prevention
    - Receipt generation and provider verification
    - Clear mock labeling (never connects to real bank or payment gateway)
    """
    def __init__(self):
        self.provider_id = "mock_booking_gateway_v1"
        self.is_live = False
        self._seat_inventory = self._generate_default_inventory()
        self.simulate_timeout = False
        self.simulate_out_of_stock = False

    def _generate_default_inventory(self) -> Dict[str, List[SeatItem]]:
        return {
            "opt_train_exp_101": [
                SeatItem(seat_number="A1", seat_type="window", coach="Car 1", extra_fee=0.0, currency="INR", is_available=True),
                SeatItem(seat_number="A2", seat_type="aisle", coach="Car 1", extra_fee=0.0, currency="INR", is_available=True),
                SeatItem(seat_number="A3", seat_type="quiet", coach="Quiet Car 2", extra_fee=50.0, currency="INR", is_available=True),
                SeatItem(seat_number="A4", seat_type="window", coach="Quiet Car 2", extra_fee=50.0, currency="INR", is_available=True),
                SeatItem(seat_number="B1", seat_type="front", coach="Car 1", extra_fee=30.0, currency="INR", is_available=True),
                SeatItem(seat_number="B2", seat_type="extra_legroom", coach="Car 1", extra_fee=75.0, currency="INR", is_available=True),
                SeatItem(seat_number="B3", seat_type="aisle", coach="Car 2", extra_fee=0.0, currency="INR", is_available=False), # Already booked
                SeatItem(seat_number="B4", seat_type="window", coach="Car 2", extra_fee=0.0, currency="INR", is_available=True),
            ],
            "opt_rideshare_prime_402": [
                SeatItem(seat_number="S1", seat_type="front", coach="Front Passenger", extra_fee=0.0, currency="INR", is_available=True),
                SeatItem(seat_number="S2", seat_type="window", coach="Rear Left", extra_fee=0.0, currency="INR", is_available=True),
                SeatItem(seat_number="S3", seat_type="window", coach="Rear Right", extra_fee=0.0, currency="INR", is_available=True),
            ]
        }

    def check_seat_availability(self, option_id: str, journey_date: str = "") -> List[SeatItem]:
        if option_id not in self._seat_inventory:
            return [
                SeatItem(seat_number="1A", seat_type="window", coach="Main", extra_fee=0.0, currency="INR", is_available=True),
                SeatItem(seat_number="1B", seat_type="aisle", coach="Main", extra_fee=0.0, currency="INR", is_available=True),
                SeatItem(seat_number="2A", seat_type="window", coach="Main", extra_fee=0.0, currency="INR", is_available=True),
            ]
        return self._seat_inventory[option_id]

    def select_best_seat(self, option_id: str, preference: str = "window") -> Optional[SeatItem]:
        seats = self.check_seat_availability(option_id, "")
        available = [s for s in seats if s.is_available]
        if not available:
            return None

        # Try exact match for preference
        for seat in available:
            if seat.seat_type.lower() == preference.lower():
                return seat

        # Fallback to first available seat
        return available[0]

    def execute_booking(self, request_data: Dict[str, Any]) -> BookingRecord:
        option_id = request_data.get("option_id", "opt_train_exp_101")
        idempotency_key = request_data.get("idempotency_key")
        user_id = request_data.get("user_id", "demo_commuter")
        user_authorized = request_data.get("user_authorized", False)
        max_budget = request_data.get("max_budget", 5000.0)
        passenger_name = request_data.get("passenger_name", "Demo Commuter")
        passenger_count = request_data.get("passenger_count", 1)
        seat_pref = request_data.get("seat_preference", "window")
        specified_seat = request_data.get("seat_number")
        is_auto_booked = request_data.get("is_auto_booked", False)
        payment_mode = request_data.get("payment_mode", "ONLINE_WALLET").upper()
        now_str = datetime.now().isoformat()

        # 1. IDEMPOTENCY CHECK - Return existing record if already processed
        if idempotency_key:
            existing = get_booking_by_idempotency_key(idempotency_key)
            if existing:
                receipt = None
                if existing.get("receipt"):
                    receipt = BookingReceipt(**existing["receipt"])
                return BookingRecord(
                    booking_id=existing["booking_id"],
                    option_id=existing["option_id"],
                    provider_id=existing["provider_id"],
                    origin=existing["origin"],
                    destination=existing["destination"],
                    journey_date=existing["journey_date"],
                    departure_time=existing["departure_time"],
                    arrival_time=existing["arrival_time"],
                    passenger_name=existing["passenger_name"],
                    passenger_count=existing["passenger_count"],
                    seat_number=existing["seat_number"],
                    seat_type=existing["seat_type"],
                    total_amount=existing["total_amount"],
                    currency=existing.get("currency", "INR"),
                    payment_mode=existing.get("payment_mode", "ONLINE_WALLET"),
                    payment_status=existing.get("payment_status", "PAID"),
                    status=existing["status"],
                    is_auto_booked=bool(existing["is_auto_booked"]),
                    is_mock=True,
                    created_at=existing["created_at"],
                    verification_code=existing["verification_code"],
                    idempotency_key=existing["idempotency_key"],
                    failure_reason=existing.get("failure_reason"),
                    receipt=receipt
                )

        # 2. Check Authorization Constraint
        if not user_authorized:
            record = BookingRecord(
                booking_id=f"BOOK-ERR-{uuid.uuid4().hex[:8].upper()}",
                option_id=option_id,
                provider_id=self.provider_id,
                origin=request_data.get("origin", "Origin"),
                destination=request_data.get("destination", "Destination"),
                journey_date=request_data.get("journey_date", datetime.now().strftime("%Y-%m-%d")),
                departure_time=request_data.get("departure_time", "08:15"),
                arrival_time=request_data.get("arrival_time", "08:50"),
                passenger_name=passenger_name,
                passenger_count=passenger_count,
                seat_number="N/A",
                seat_type="N/A",
                total_amount=0.0,
                currency="INR",
                payment_mode=payment_mode,
                payment_status="FAILED",
                status="FAILED",
                is_auto_booked=is_auto_booked,
                is_mock=True,
                created_at=now_str,
                failure_reason="Unauthorized: User authorization required before executing seat reservation."
            )
            save_booking(record.model_dump())
            return record

        # 3. Check Seat Availability & Allocate
        chosen_seat = None
        available_seats = [s for s in self.check_seat_availability(option_id, "") if s.is_available]

        if specified_seat:
            for s in available_seats:
                if s.seat_number.upper() == specified_seat.upper():
                    chosen_seat = s
                    break

        if not chosen_seat:
            chosen_seat = self.select_best_seat(option_id, seat_pref)

        if not chosen_seat:
            record = BookingRecord(
                booking_id=f"BOOK-NOSEAT-{uuid.uuid4().hex[:8].upper()}",
                option_id=option_id,
                provider_id=self.provider_id,
                origin=request_data.get("origin", "Origin"),
                destination=request_data.get("destination", "Destination"),
                journey_date=request_data.get("journey_date", datetime.now().strftime("%Y-%m-%d")),
                departure_time=request_data.get("departure_time", "08:15"),
                arrival_time=request_data.get("arrival_time", "08:50"),
                passenger_name=passenger_name,
                passenger_count=passenger_count,
                seat_number="NONE",
                seat_type="NONE",
                total_amount=0.0,
                currency="INR",
                payment_mode=payment_mode,
                payment_status="FAILED",
                status="FAILED",
                is_auto_booked=is_auto_booked,
                is_mock=True,
                created_at=now_str,
                failure_reason=f"No seats matching preference '{seat_pref}' currently available."
            )
            save_booking(record.model_dump())
            return record

        # 4. Calculate Price & Budget Validation
        base_fare = float(request_data.get("total_fare", 180.0))
        total_price = (base_fare + chosen_seat.extra_fee) * passenger_count

        if total_price > max_budget:
            record = BookingRecord(
                booking_id=f"BOOK-BUDGET-{uuid.uuid4().hex[:8].upper()}",
                option_id=option_id,
                provider_id=self.provider_id,
                origin=request_data.get("origin", "Origin"),
                destination=request_data.get("destination", "Destination"),
                journey_date=request_data.get("journey_date", datetime.now().strftime("%Y-%m-%d")),
                departure_time=request_data.get("departure_time", "08:15"),
                arrival_time=request_data.get("arrival_time", "08:50"),
                passenger_name=passenger_name,
                passenger_count=passenger_count,
                seat_number=chosen_seat.seat_number,
                seat_type=chosen_seat.seat_type,
                total_amount=total_price,
                currency="INR",
                payment_mode=payment_mode,
                payment_status="FAILED",
                status="FAILED",
                is_auto_booked=is_auto_booked,
                is_mock=True,
                created_at=now_str,
                failure_reason=f"Booking total ₹{total_price:.2f} exceeds authorized budget limit of ₹{max_budget:.2f}."
            )
            save_booking(record.model_dump())
            return record

        # 5. Process Payment (Online Demo Wallet vs Offline Pay Later)
        booking_id = f"MOCK-BKG-{uuid.uuid4().hex[:8].upper()}"
        txn_id = None
        payment_status = "PAID"

        if payment_mode == "ONLINE_WALLET":
            # Atomic Wallet deduction
            wallet_res = process_wallet_payment(
                user_id=user_id,
                amount=total_price,
                booking_id=booking_id,
                description=f"Seat booking for {option_id} (Seat {chosen_seat.seat_number})",
                idempotency_key=f"pay_{idempotency_key}" if idempotency_key else None
            )

            if not wallet_res.get("success"):
                record = BookingRecord(
                    booking_id=booking_id,
                    option_id=option_id,
                    provider_id=self.provider_id,
                    origin=request_data.get("origin", "Origin"),
                    destination=request_data.get("destination", "Destination"),
                    journey_date=request_data.get("journey_date", datetime.now().strftime("%Y-%m-%d")),
                    departure_time=request_data.get("departure_time", "08:15"),
                    arrival_time=request_data.get("arrival_time", "08:50"),
                    passenger_name=passenger_name,
                    passenger_count=passenger_count,
                    seat_number=chosen_seat.seat_number,
                    seat_type=chosen_seat.seat_type,
                    total_amount=total_price,
                    currency="INR",
                    payment_mode="ONLINE_WALLET",
                    payment_status="FAILED",
                    status="FAILED",
                    is_auto_booked=is_auto_booked,
                    is_mock=True,
                    created_at=now_str,
                    failure_reason=wallet_res.get("error", "Payment failed.")
                )
                save_booking(record.model_dump())
                return record

            txn_id = wallet_res.get("txn_id")
            payment_status = "PAID"

        elif payment_mode == "OFFLINE_PAY_LATER":
            # No deduction, outstanding pending payment recorded
            payment_status = "PENDING_PAYMENT"
            txn_id = "OFFLINE_PAY_LATER"

        # 6. Lock seat in memory inventory
        chosen_seat.is_available = False

        # 7. Generate Verification Code and Receipt
        verification_code = f"VERIF-{uuid.uuid4().hex[:6].upper()}"
        receipt = BookingReceipt(
            receipt_id=f"RCPT-{uuid.uuid4().hex[:8].upper()}",
            booking_id=booking_id,
            passenger_name=passenger_name,
            origin=request_data.get("origin", "North Station"),
            destination=request_data.get("destination", "Financial District"),
            departure_time=request_data.get("departure_time", "08:25"),
            arrival_time=request_data.get("arrival_time", "09:00"),
            seat_number=chosen_seat.seat_number,
            seat_type=chosen_seat.seat_type,
            base_fare=base_fare,
            seat_fee=chosen_seat.extra_fee,
            total_paid=total_price,
            currency="INR",
            payment_mode=payment_mode,
            payment_status=payment_status,
            txn_id=txn_id,
            timestamp=now_str
        )

        record = BookingRecord(
            booking_id=booking_id,
            option_id=option_id,
            provider_id=self.provider_id,
            origin=request_data.get("origin", "North Station"),
            destination=request_data.get("destination", "Financial District"),
            journey_date=request_data.get("journey_date", datetime.now().strftime("%Y-%m-%d")),
            departure_time=request_data.get("departure_time", "08:25"),
            arrival_time=request_data.get("arrival_time", "09:00"),
            passenger_name=passenger_name,
            passenger_count=passenger_count,
            seat_number=chosen_seat.seat_number,
            seat_type=chosen_seat.seat_type,
            total_amount=round(total_price, 2),
            currency="INR",
            payment_mode=payment_mode,
            payment_status=payment_status,
            status="CONFIRMED",
            is_auto_booked=is_auto_booked,
            is_mock=True,
            created_at=now_str,
            verification_code=verification_code,
            idempotency_key=idempotency_key,
            receipt=receipt
        )

        save_booking(record.model_dump())
        return record

    def verify_booking(self, booking_id: str) -> Dict[str, Any]:
        record = get_booking_by_id(booking_id)
        if not record:
            return {
                "booking_id": booking_id,
                "verified": False,
                "status": "NOT_FOUND",
                "message": "Booking ID not found in system.",
                "is_mock": True
            }
        return {
            "booking_id": record["booking_id"],
            "verified": record["status"] == "CONFIRMED",
            "status": record["status"],
            "passenger_name": record["passenger_name"],
            "seat_number": record["seat_number"],
            "payment_mode": record.get("payment_mode", "ONLINE_WALLET"),
            "payment_status": record.get("payment_status", "PAID"),
            "verification_code": record["verification_code"],
            "total_amount": record["total_amount"],
            "currency": record.get("currency", "INR"),
            "receipt": record.get("receipt"),
            "is_mock": bool(record.get("is_mock", True))
        }
