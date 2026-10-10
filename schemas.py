from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class AgentStepEnum(str):
    UNDERSTAND = "UNDERSTAND"
    PLAN = "PLAN"
    SELECT_TOOLS = "SELECT_TOOLS"
    EXECUTE = "EXECUTE"
    OBSERVE = "OBSERVE"
    RETRIEVE_RAG = "RETRIEVE_RAG"
    EVALUATE = "EVALUATE"
    DECIDE = "DECIDE"
    ACT = "ACT"
    VERIFY = "VERIFY"
    MONITOR = "MONITOR"
    REPLAN = "REPLAN"


class SeatPreferenceEnum(str):
    WINDOW = "window"
    AISLE = "aisle"
    QUIET = "quiet"
    FRONT = "front"
    EXTRA_LEGROOM = "extra_legroom"
    ANY = "any"


class RankingStrategyEnum(str):
    BALANCED = "balanced"
    CHEAPEST = "cheapest"
    FASTEST = "fastest"
    PREFERENCE = "preference"


class PaymentModeEnum(str):
    ONLINE_WALLET = "ONLINE_WALLET"
    OFFLINE_PAY_LATER = "OFFLINE_PAY_LATER"


class PaymentStatusEnum(str):
    PAID = "PAID"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


# ==========================================
# AUTH & WALLET SCHEMAS
# ==========================================
class DemoLoginRequest(BaseModel):
    username: str = "demo_commuter"
    password: str = "demo123"


class DemoUserResponse(BaseModel):
    username: str
    display_name: str
    email: str
    role: str = "commuter"
    wallet_balance: float
    currency: str = "INR"
    is_simulated: bool = True


class WalletTopupRequest(BaseModel):
    user_id: str = "demo_commuter"
    amount: float = Field(..., gt=0)
    description: Optional[str] = "Simulated Wallet Top-up"


class WalletTransactionRecord(BaseModel):
    txn_id: str
    user_id: str
    txn_type: str  # CREDIT, DEBIT, REFUND
    amount: float
    currency: str = "INR"
    balance_after: float
    booking_id: Optional[str] = None
    description: str
    status: str  # SUCCESS, FAILED
    is_simulated: bool = True
    timestamp: str


class BookingReceipt(BaseModel):
    receipt_id: str
    booking_id: str
    passenger_name: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    seat_number: str
    seat_type: str
    base_fare: float
    seat_fee: float = 0.0
    total_paid: float
    currency: str = "INR"
    payment_mode: str  # ONLINE_WALLET, OFFLINE_PAY_LATER
    payment_status: str  # PAID, PENDING_PAYMENT
    txn_id: Optional[str] = None
    timestamp: str
    is_simulated: bool = True
    disclaimer: str = "SIMULATED RECEIPT - FOR DEMO PURPOSES ONLY"


# ==========================================
# COMMUTE & BOOKING SCHEMAS
# ==========================================
class CommutePreferences(BaseModel):
    user_id: str = "demo_commuter"
    max_budget: float = 2000.0
    latest_arrival_time: str = "09:00"  # HH:MM
    preferred_modes: List[str] = Field(default_factory=lambda: ["metro", "express_train", "bus", "rideshare"])
    seat_preference: str = "window"
    payment_mode_preference: str = "ONLINE_WALLET"  # ONLINE_WALLET or OFFLINE_PAY_LATER
    auto_book_enabled: bool = False
    auto_book_authorized: bool = False  # User explicit authorization
    ranking_strategy: str = "balanced"
    max_walking_minutes: int = 15
    notification_channel: str = "ui"


class CommuteRequest(BaseModel):
    user_id: str = "demo_commuter"
    origin: str = "North Station"
    destination: str = "Financial District"
    journey_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    desired_arrival_time: str = "09:00"
    passenger_count: int = 1
    passenger_name: str = "Demo Commuter"
    passenger_email: str = "demo.commuter@example.com"
    budget_limit: Optional[float] = 2000.0
    seat_preference: Optional[str] = "window"
    ranking_strategy: Optional[str] = "balanced"
    payment_mode: Optional[str] = "ONLINE_WALLET"  # ONLINE_WALLET or OFFLINE_PAY_LATER
    auto_book: Optional[bool] = False
    auto_book_authorized: Optional[bool] = False
    context_notes: Optional[str] = None


class RouteSegment(BaseModel):
    mode: str
    from_stop: str
    to_stop: str
    duration_min: int
    fare: float
    line_name: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None


class CommuteOption(BaseModel):
    id: str
    mode: str  # metro, express_train, bus, rideshare, bike, walking
    title: str
    origin: str
    destination: str
    departure_time: str  # HH:MM
    arrival_time: str  # HH:MM
    duration_minutes: int
    base_fare: float
    total_fare: float
    currency: str = "INR"
    reliability_score: float = 0.9  # 0.0 - 1.0
    weather_impact: str = "Normal"
    traffic_delay_min: int = 0
    available_seats: int = 0
    requires_booking: bool = False
    provider_id: str = "mock_transit_adapter"
    is_live_provider: bool = False  # Clearly labeled
    segments: List[RouteSegment] = Field(default_factory=list)
    score: float = 0.0
    is_eligible: bool = True
    rejection_reasons: List[str] = Field(default_factory=list)


class SeatItem(BaseModel):
    seat_number: str
    seat_type: str  # window, aisle, middle, front, quiet
    coach: str
    extra_fee: float = 0.0
    currency: str = "INR"
    is_available: bool = True


class BookingExecutionRequest(BaseModel):
    option_id: str
    journey_date: str
    user_id: str = "demo_commuter"
    passenger_count: int = 1
    passenger_name: str = "Demo Commuter"
    passenger_email: str = "demo.commuter@example.com"
    seat_number: Optional[str] = None
    seat_preference: Optional[str] = "window"
    max_budget: Optional[float] = 2000.0
    payment_mode: str = "ONLINE_WALLET"  # ONLINE_WALLET or OFFLINE_PAY_LATER
    is_auto_booked: bool = False
    user_authorized: bool = True
    idempotency_key: Optional[str] = None


class BookingRecord(BaseModel):
    booking_id: str
    option_id: str
    provider_id: str
    origin: str
    destination: str
    journey_date: str
    departure_time: str
    arrival_time: str
    passenger_name: str
    passenger_count: int
    seat_number: str
    seat_type: str
    total_amount: float
    currency: str = "INR"
    payment_mode: str = "ONLINE_WALLET"  # ONLINE_WALLET, OFFLINE_PAY_LATER
    payment_status: str = "PAID"        # PAID, PENDING_PAYMENT, FAILED
    status: str                          # CONFIRMED, FAILED, PENDING, CANCELLED
    is_auto_booked: bool
    is_mock: bool = True
    created_at: str
    verification_code: Optional[str] = None
    failure_reason: Optional[str] = None
    idempotency_key: Optional[str] = None
    receipt: Optional[BookingReceipt] = None


class ToolCallRecord(BaseModel):
    tool_name: str
    input_params: Dict[str, Any]
    output_result: Any
    execution_time_ms: float
    timestamp: str
    status: str = "SUCCESS"
    error_message: Optional[str] = None


class AgentTraceStep(BaseModel):
    step_number: int
    stage: str  # AgentStepEnum
    description: str
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    state_summary: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    timestamp: str


class RAGDocument(BaseModel):
    id: str
    filename: str
    source_type: str  # txt, md, pdf
    chunk_count: int
    created_at: str


class RAGQueryResult(BaseModel):
    query: str
    answer: str
    sources: List[Dict[str, Any]]
    confidence_score: float
    rag_used: bool


class PlanResponse(BaseModel):
    session_id: str
    request: CommuteRequest
    recommended_option: Optional[CommuteOption]
    all_options: List[CommuteOption]
    steps_executed: List[AgentTraceStep]
    rag_context: Optional[RAGQueryResult] = None
    booking_result: Optional[BookingRecord] = None
    decision_explanation: str
    status: str  # SUCCESS, REJECTED_CONSTRAINTS, FAILED
    disruption_detected: bool = False
    persisted_task_id: Optional[str] = None


class DisruptionEvent(BaseModel):
    disruption_type: str  # delay, weather_storm, road_closure, price_surge, cancelled_service
    severity: str  # minor, moderate, severe
    affected_mode: str
    delay_minutes: int
    location: str
    description: str


class ReplanRequest(BaseModel):
    session_id: str
    disruption: DisruptionEvent
    allow_auto_rebook: bool = False
    payment_mode: Optional[str] = "ONLINE_WALLET"


# ==========================================
# LIVE TRACKING TELEMETRY SCHEMAS
# ==========================================
class LiveTrackingTelemetry(BaseModel):
    trip_id: str
    booking_id: Optional[str] = None
    origin: str
    destination: str
    current_lat: float
    current_lon: float
    current_stop: str
    next_stop: str
    progress_percentage: float
    speed_kmh: float
    eta_minutes: int
    status: str  # SCHEDULED, IN_TRANSIT, DELAYED, COMPLETED
    stops: List[str] = Field(default_factory=list)
    updated_at: str
