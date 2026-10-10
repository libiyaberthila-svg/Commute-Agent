import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.config import settings, FRONTEND_DIR
from backend.database import (
    init_db,
    authenticate_user,
    get_demo_user,
    get_wallet,
    topup_wallet,
    get_wallet_transactions,
    get_trip_telemetry,
    update_trip_telemetry
)
from backend.schemas import (
    CommuteRequest,
    PlanResponse,
    ReplanRequest,
    CommutePreferences,
    BookingExecutionRequest,
    BookingRecord,
    RAGQueryResult,
    RAGDocument,
    DemoLoginRequest,
    DemoUserResponse,
    WalletTopupRequest,
    WalletTransactionRecord,
    LiveTrackingTelemetry
)
from backend.agent import agent
from backend.tools.registry import registry
from backend.rag_service import rag_service
from backend.memory_service import memory_service
from backend.providers.mock_booking import MockBookingProvider

# Initialize database tables on startup
init_db()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Locally runnable Agentic AI for Daily Commute Planning, RAG Policy Retrieval, Simulated Wallet Payments, and Autonomous Seat Reservations."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

booking_provider = MockBookingProvider()


@app.get("/api/health")
def health_check():
    wallet = get_wallet("demo_commuter")
    return {
        "status": "HEALTHY",
        "app_name": settings.app_name,
        "version": settings.version,
        "mode": "agentic",
        "llm_enabled": settings.use_llm,
        "sqlite_database": "connected",
        "currency": settings.default_currency,
        "currency_symbol": settings.currency_symbol,
        "demo_wallet_balance": wallet["balance"],
        "rag_indexed_docs": len(rag_service.list_documents()),
        "registered_tools_count": len(registry.list_tools())
    }


# ==========================================
# AUTH & DEMO ACCOUNT ENDPOINTS
# ==========================================
@app.post("/api/auth/login", response_model=DemoUserResponse)
def demo_login(req: DemoLoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials. Use demo_commuter / demo123.")
    wallet = get_wallet(user["username"])
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "email": user["email"],
        "role": user["role"],
        "wallet_balance": wallet["balance"],
        "currency": wallet["currency"],
        "is_simulated": True
    }


@app.get("/api/auth/user", response_model=DemoUserResponse)
def get_current_user(username: str = "demo_commuter"):
    user = get_demo_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    wallet = get_wallet(username)
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "email": user["email"],
        "role": user["role"],
        "wallet_balance": wallet["balance"],
        "currency": wallet["currency"],
        "is_simulated": True
    }


# ==========================================
# DEMO WALLET ENDPOINTS
# ==========================================
@app.get("/api/wallet")
def get_user_wallet(user_id: str = "demo_commuter"):
    return get_wallet(user_id)


@app.post("/api/wallet/topup")
def topup_user_wallet(req: WalletTopupRequest):
    try:
        res = topup_wallet(user_id=req.user_id, amount=req.amount, description=req.description or "Simulated Wallet Top-up")
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/wallet/transactions", response_model=List[WalletTransactionRecord])
def get_transactions(user_id: str = "demo_commuter", limit: int = 50):
    txns = get_wallet_transactions(user_id=user_id, limit=limit)
    return txns


# ==========================================
# AGENT PLANNING & RE-PLANNING ENDPOINTS
# ==========================================
@app.post("/api/plan", response_model=PlanResponse)
def plan_commute(request: CommuteRequest):
    try:
        response = agent.run_workflow(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/replan", response_model=PlanResponse)
def replan_commute(request: ReplanRequest):
    try:
        response = agent.replan_on_disruption(
            session_id=request.session_id,
            disruption=request.disruption,
            allow_auto_rebook=request.allow_auto_rebook,
            payment_mode=request.payment_mode or "ONLINE_WALLET"
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = memory_service.recover_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ==========================================
# AGENT TOOLS ENDPOINTS
# ==========================================
@app.get("/api/tools")
def list_tools():
    return {
        "count": len(registry.list_tools()),
        "tools": registry.list_tools()
    }


@app.post("/api/tools/execute")
def execute_tool(payload: Dict[str, Any]):
    tool_name = payload.get("tool_name")
    params = payload.get("params", {})
    session_id = payload.get("session_id", "manual_tool_invocation")
    if not tool_name:
        raise HTTPException(status_code=400, detail="tool_name is required")
    try:
        result = registry.execute(tool_name, session_id=session_id, **params)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/traces")
def get_traces(session_id: Optional[str] = None, limit: int = 50):
    logs = memory_service.get_recent_traces(session_id=session_id, limit=limit)
    return {"count": len(logs), "traces": logs}


# ==========================================
# RAG ENDPOINTS
# ==========================================
@app.get("/api/rag/documents", response_model=List[RAGDocument])
def get_rag_documents():
    return rag_service.list_documents()


@app.post("/api/rag/upload")
async def upload_rag_document(file: UploadFile = File(...)):
    try:
        dest_path = Path(settings.knowledge_base_dir) / file.filename
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        res = rag_service.ingest_file(str(dest_path))
        return {
            "status": "SUCCESS",
            "message": f"Document '{file.filename}' successfully ingested and indexed.",
            "details": res
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rag/query", response_model=RAGQueryResult)
def query_rag(payload: Dict[str, Any]):
    query_text = payload.get("query", "")
    if not query_text:
        raise HTTPException(status_code=400, detail="query string is required")
    top_k = payload.get("top_k", 3)
    return rag_service.query(query_text, top_k=top_k)


# ==========================================
# AUTONOMOUS SEAT BOOKING ENDPOINTS
# ==========================================
@app.post("/api/booking/availability")
def get_seat_availability(payload: Dict[str, Any]):
    option_id = payload.get("option_id", "opt_train_exp_101")
    seats = booking_provider.check_seat_availability(option_id, "")
    return {
        "option_id": option_id,
        "total_seats": len(seats),
        "available_seats": len([s for s in seats if s.is_available]),
        "seats": [s.model_dump() for s in seats],
        "is_mock_provider": True
    }


@app.post("/api/booking/execute", response_model=BookingRecord)
def execute_booking(request: BookingExecutionRequest):
    try:
        rec = booking_provider.execute_booking(request.model_dump())
        return rec
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/booking/status/{booking_id}")
def check_booking_status(booking_id: str):
    res = booking_provider.verify_booking(booking_id)
    return res


@app.get("/api/booking/history")
def get_booking_history(limit: int = 50):
    bookings = memory_service.list_all_bookings(limit=limit)
    return {"count": len(bookings), "bookings": bookings}


# ==========================================
# LIVE TRACKING TELEMETRY ENDPOINTS
# ==========================================
@app.get("/api/tracking/{trip_id}")
def get_live_tracking(trip_id: str):
    data = get_trip_telemetry(trip_id)
    if not data:
        # Generate on-demand default telemetry for the trip
        data = {
            "trip_id": trip_id,
            "origin": "North Station",
            "destination": "Financial District",
            "current_lat": 12.9716,
            "current_lon": 77.5946,
            "current_stop": "North Station (Departed)",
            "next_stop": "Tech Park Interchange",
            "progress_percentage": 35.0,
            "speed_kmh": 58.5,
            "eta_minutes": 18,
            "status": "IN_TRANSIT",
            "stops": ["North Station", "Tech Park Interchange", "Metro Central", "Financial District"],
            "updated_at": "Just now"
        }
    return data


@app.post("/api/tracking/simulate")
def simulate_tracking_step(payload: Dict[str, Any]):
    trip_id = payload.get("trip_id", "TRIP-default")
    current = get_trip_telemetry(trip_id)
    prog = float(current["progress_percentage"] if current else 10.0) + 20.0
    if prog >= 100.0:
        prog = 100.0
        status = "COMPLETED"
        eta = 0
        speed = 0.0
        c_stop = payload.get("destination", "Financial District")
        n_stop = "Arrived"
    else:
        status = "IN_TRANSIT"
        eta = max(2, int((100.0 - prog) * 0.4))
        speed = 52.0
        c_stop = "Transit Corridor Sector 4"
        n_stop = payload.get("destination", "Financial District")

    updated = {
        "trip_id": trip_id,
        "booking_id": payload.get("booking_id"),
        "origin": payload.get("origin", "North Station"),
        "destination": payload.get("destination", "Financial District"),
        "current_lat": 12.9716 + (prog * 0.0005),
        "current_lon": 77.5946 + (prog * 0.0004),
        "current_stop": c_stop,
        "next_stop": n_stop,
        "progress_percentage": round(prog, 1),
        "speed_kmh": speed,
        "eta_minutes": eta,
        "status": status
    }
    update_trip_telemetry(updated)
    return updated


# ==========================================
# USER PREFERENCES & MEMORY
# ==========================================
@app.get("/api/preferences")
def get_preferences(user_id: str = "demo_commuter"):
    return memory_service.get_preferences(user_id)


@app.post("/api/preferences")
def update_preferences(prefs: CommutePreferences):
    memory_service.update_preferences(prefs.model_dump())
    return {"status": "UPDATED", "preferences": memory_service.get_preferences(prefs.user_id)}


# ==========================================
# STATIC FRONTEND SERVING
# ==========================================
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.get("/")
    def serve_frontend_index():
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return JSONResponse({"message": "Frontend index.html not found"}, status_code=404)
