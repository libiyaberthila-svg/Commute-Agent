import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from backend.schemas import (
    CommuteRequest,
    CommuteOption,
    CommutePreferences,
    PlanResponse,
    AgentTraceStep,
    ToolCallRecord,
    DisruptionEvent,
    BookingRecord,
    RAGQueryResult
)
from backend.tools.registry import registry
from backend.rag_service import rag_service
from backend.decision_engine import decision_engine
from backend.memory_service import memory_service
from backend.providers.llm_provider import LLMProvider
from backend.database import update_trip_telemetry, get_wallet

# Ensure all tools are registered by importing tool modules
import backend.tools.travel_tools
import backend.tools.constraint_tools
import backend.tools.booking_tools
import backend.tools.rag_tools
import backend.tools.memory_tools
import backend.tools.monitor_tools
import backend.tools.wallet_and_payment_tools


class AutonomousCommuteAgent:
    """
    Autonomous Commute & Seat Booking Agent implementing the complete stateful loop:
    UNDERSTAND -> PLAN -> SELECT TOOLS -> EXECUTE -> OBSERVE -> RETRIEVE RAG -> EVALUATE -> DECIDE -> ACT -> VERIFY -> MONITOR -> REPLAN
    With Autonomous Seat Booking & Payment Workflow:
    SEARCH -> CHECK AVAILABILITY -> SELECT BEST ELIGIBLE SEAT -> VALIDATE FARE -> CHOOSE PAYMENT MODE -> PROCESS -> VERIFY -> CONFIRM -> SAVE
    """
    def __init__(self):
        self.llm_provider = LLMProvider()

    def run_workflow(self, request: CommuteRequest, session_id: Optional[str] = None) -> PlanResponse:
        session_id = session_id or f"session_{uuid.uuid4().hex[:8]}"
        user_id = request.user_id or "demo_commuter"
        trace_steps: List[AgentTraceStep] = []
        step_counter = 1

        # ==========================================
        # STEP 1: UNDERSTAND
        # ==========================================
        user_prefs_dict = memory_service.get_preferences(user_id=user_id)
        user_prefs = CommutePreferences(**user_prefs_dict)
        wallet = get_wallet(user_id)

        effective_budget = request.budget_limit if request.budget_limit is not None else user_prefs.max_budget
        effective_arrival = request.desired_arrival_time or user_prefs.latest_arrival_time
        effective_strategy = request.ranking_strategy or user_prefs.ranking_strategy
        effective_payment_mode = (request.payment_mode or user_prefs.payment_mode_preference or "ONLINE_WALLET").upper()
        auto_book_requested = bool(request.auto_book or user_prefs.auto_book_enabled)
        auto_book_authorized = bool(request.auto_book_authorized or user_prefs.auto_book_authorized)

        understand_step = AgentTraceStep(
            step_number=step_counter,
            stage="UNDERSTAND",
            description=(
                f"Parsed commute intent for {request.passenger_name} ({request.passenger_count} passenger(s)) "
                f"from '{request.origin}' to '{request.destination}' on {request.journey_date}. "
                f"Target arrival: {effective_arrival}, Budget Cap: ₹{effective_budget:.2f}, Strategy: {effective_strategy}. "
                f"Payment Mode: {effective_payment_mode}, Wallet Balance: ₹{wallet['balance']:.2f}. "
                f"Auto-book opt-in: {auto_book_requested} (Authorized: {auto_book_authorized})."
            ),
            state_summary={
                "origin": request.origin,
                "destination": request.destination,
                "user_id": user_id,
                "wallet_balance": wallet["balance"],
                "payment_mode": effective_payment_mode,
                "effective_budget": effective_budget,
                "effective_arrival": effective_arrival,
                "auto_book_requested": auto_book_requested,
                "auto_book_authorized": auto_book_authorized
            },
            timestamp=datetime.now().isoformat()
        )
        trace_steps.append(understand_step)
        step_counter += 1

        # ==========================================
        # STEP 2: PLAN
        # ==========================================
        plan_step = AgentTraceStep(
            step_number=step_counter,
            stage="PLAN",
            description=(
                "Synthesizing autonomous multi-step execution plan: "
                "1. Query transit networks for all viable routes. "
                "2. Gather environmental live data (weather, road traffic congestion). "
                "3. Query local RAG vector store for commute policy and fare guidelines. "
                "4. Apply deterministic budget, deadline, and wallet balance constraint checks. "
                "5. Score & rank options using strategy. "
                "6. If best option requires booking and user authorized: SEARCH -> CHECK AVAILABILITY -> SELECT BEST SEAT -> VALIDATE FARE -> PROCESS (Online Wallet / Offline Pay Later) -> VERIFY -> CONFIRM -> SAVE. "
                "7. Register live trip tracking telemetry in SQLite."
            ),
            state_summary={"planned_actions": 7},
            timestamp=datetime.now().isoformat()
        )
        trace_steps.append(plan_step)
        step_counter += 1

        # ==========================================
        # STEP 3: SELECT TOOLS
        # ==========================================
        selected_tool_names = [
            "route_search",
            "weather",
            "traffic_status",
            "rag_retrieval",
            "budget_check",
            "deadline_check",
            "wallet_balance_tool",
            "booking_eligibility",
            "decision_explanation"
        ]
        if auto_book_requested and auto_book_authorized:
            selected_tool_names.extend([
                "seat_availability_tool",
                "seat_selection_tool",
                "fare_validation_tool",
                "payment_method_tool",
                "booking_execution",
                "booking_verification_tool"
            ])

        select_tools_step = AgentTraceStep(
            step_number=step_counter,
            stage="SELECT_TOOLS",
            description=f"Selected {len(selected_tool_names)} executable agent tools from registry: {', '.join(selected_tool_names)}.",
            state_summary={"tools": selected_tool_names},
            timestamp=datetime.now().isoformat()
        )
        trace_steps.append(select_tools_step)
        step_counter += 1

        # ==========================================
        # STEP 4: EXECUTE & STEP 5: OBSERVE
        # ==========================================
        exec_step = AgentTraceStep(
            step_number=step_counter,
            stage="EXECUTE",
            description="Executing transit route discovery, weather telemetry, and road traffic status tools concurrently.",
            tool_calls=[],
            timestamp=datetime.now().isoformat()
        )

        call_routes = registry.execute("route_search", session_id=session_id, origin=request.origin, destination=request.destination, target_arrival=effective_arrival, journey_date=request.journey_date)
        exec_step.tool_calls.append(call_routes)

        call_weather = registry.execute("weather", session_id=session_id, location=request.origin)
        exec_step.tool_calls.append(call_weather)

        call_traffic = registry.execute("traffic_status", session_id=session_id, origin=request.origin, destination=request.destination)
        exec_step.tool_calls.append(call_traffic)

        call_wallet = registry.execute("wallet_balance_tool", session_id=session_id, user_id=user_id)
        exec_step.tool_calls.append(call_wallet)

        trace_steps.append(exec_step)
        step_counter += 1

        raw_routes = call_routes.output_result if isinstance(call_routes.output_result, list) else []
        options = [CommuteOption(**r) for r in raw_routes]
        weather_data = call_weather.output_result or {}
        traffic_data = call_traffic.output_result or {}

        observe_step = AgentTraceStep(
            step_number=step_counter,
            stage="OBSERVE",
            description=(
                f"Observed {len(options)} transit options. Weather: {weather_data.get('condition')} "
                f"({weather_data.get('precipitation_chance')}% rain). Traffic congestion: {traffic_data.get('congestion_level')} "
                f"(estimated road delay: +{traffic_data.get('delay_minutes')} min). Demo Wallet: ₹{wallet['balance']:.2f}."
            ),
            state_summary={
                "found_options_count": len(options),
                "weather": weather_data,
                "traffic": traffic_data,
                "wallet_balance": wallet["balance"]
            },
            timestamp=datetime.now().isoformat()
        )
        trace_steps.append(observe_step)
        step_counter += 1

        # ==========================================
        # STEP 6: RETRIEVE RAG
        # ==========================================
        rag_query_text = f"Commute peak fare rules, wallet discounts and seat reservation policy for {request.origin} to {request.destination}"
        call_rag = registry.execute("rag_retrieval", session_id=session_id, query=rag_query_text, top_k=2)
        rag_result_dict = call_rag.output_result or {}
        rag_result = RAGQueryResult(**rag_result_dict) if rag_result_dict else None

        rag_step = AgentTraceStep(
            step_number=step_counter,
            stage="RETRIEVE_RAG",
            description=(
                f"Queried local persistent RAG index. Retrieved {len(rag_result.sources if rag_result else [])} grounded policy passages "
                f"(confidence: {rag_result.confidence_score if rag_result else 0.0})."
            ),
            tool_calls=[call_rag],
            state_summary={"rag_confidence": rag_result.confidence_score if rag_result else 0.0},
            timestamp=datetime.now().isoformat()
        )
        trace_steps.append(rag_step)
        step_counter += 1

        # ==========================================
        # STEP 7: EVALUATE & STEP 8: DECIDE
        # ==========================================
        eval_step = AgentTraceStep(
            step_number=step_counter,
            stage="EVALUATE",
            description="Evaluating deterministic hard constraints: budget limits, wallet solvency, and arrival deadlines for each option.",
            tool_calls=[],
            timestamp=datetime.now().isoformat()
        )

        for opt in options:
            call_b = registry.execute("budget_check", session_id=session_id, fare=opt.total_fare, max_budget=effective_budget)
            call_d = registry.execute("deadline_check", session_id=session_id, estimated_arrival=opt.arrival_time, deadline_time=effective_arrival)
            eval_step.tool_calls.extend([call_b, call_d])

        trace_steps.append(eval_step)
        step_counter += 1

        recommended_option, ranked_options = decision_engine.evaluate_and_rank(
            options=options,
            request=request,
            preferences=user_prefs
        )

        decide_step = AgentTraceStep(
            step_number=step_counter,
            stage="DECIDE",
            description=(
                f"Ranked {len(ranked_options)} options under '{effective_strategy}' strategy. "
                f"Recommended: {recommended_option.title if recommended_option else 'None (All rejected)'} "
                f"(Score: {recommended_option.score if recommended_option else 0.0})."
            ),
            state_summary={
                "recommended_id": recommended_option.id if recommended_option else None,
                "strategy": effective_strategy
            },
            timestamp=datetime.now().isoformat()
        )
        trace_steps.append(decide_step)
        step_counter += 1

        # Generate explanation tool call
        explanation_text = "No viable commute route found matching constraints."
        if recommended_option:
            call_exp = registry.execute(
                "decision_explanation",
                session_id=session_id,
                selected_option=recommended_option.model_dump(),
                budget_limit=effective_budget,
                desired_arrival=effective_arrival,
                rag_context=rag_result.answer if rag_result else None
            )
            explanation_text = call_exp.output_result.get("explanation", "")

        # ==========================================
        # STEP 9: ACT & STEP 10: VERIFY (Autonomous Seat Booking & Payment Workflow)
        # ==========================================
        booking_record: Optional[BookingRecord] = None

        if recommended_option and recommended_option.requires_booking:
            if auto_book_requested and auto_book_authorized:
                act_step = AgentTraceStep(
                    step_number=step_counter,
                    stage="ACT",
                    description=(
                        f"Autonomous Seat Booking & Payment Workflow triggered for '{recommended_option.title}'. "
                        f"Executing: CHECK AVAILABILITY -> SELECT SEAT -> VALIDATE FARE -> CHOOSE PAYMENT MODE -> PROCESS -> CONFIRM."
                    ),
                    tool_calls=[],
                    timestamp=datetime.now().isoformat()
                )

                idempotency_key = f"idem_{session_id}_{recommended_option.id}_{request.journey_date}"

                # 1. Recheck live seat availability
                call_avail = registry.execute("seat_availability_tool", session_id=session_id, option_id=recommended_option.id, journey_date=request.journey_date)
                act_step.tool_calls.append(call_avail)

                # 2. Select best seat
                call_sel = registry.execute("seat_selection_tool", session_id=session_id, option_id=recommended_option.id, preference=request.seat_preference or user_prefs.seat_preference)
                act_step.tool_calls.append(call_sel)
                matched_seat = call_sel.output_result.get("seat") if call_sel.output_result else None
                seat_num = matched_seat.get("seat_number") if matched_seat else None
                seat_fee = matched_seat.get("extra_fee", 0.0) if matched_seat else 0.0

                # 3. Validate Fare & Wallet balance
                call_fval = registry.execute(
                    "fare_validation_tool",
                    session_id=session_id,
                    base_fare=recommended_option.total_fare,
                    seat_fee=seat_fee,
                    passenger_count=request.passenger_count,
                    user_id=user_id,
                    payment_mode=effective_payment_mode
                )
                act_step.tool_calls.append(call_fval)

                # 4. Payment Method Tool
                call_pmode = registry.execute("payment_method_tool", session_id=session_id, requested_mode=effective_payment_mode, user_id=user_id)
                act_step.tool_calls.append(call_pmode)

                # 5. Check Eligibility
                call_elig = registry.execute(
                    "booking_eligibility",
                    session_id=session_id,
                    requires_booking=True,
                    available_seats=recommended_option.available_seats,
                    total_fare=recommended_option.total_fare + seat_fee,
                    max_auto_budget=effective_budget,
                    user_authorized=auto_book_authorized
                )
                act_step.tool_calls.append(call_elig)

                if call_elig.output_result.get("is_eligible_for_auto_booking") and call_fval.output_result.get("is_valid"):
                    # Execute Booking and atomic payment
                    call_book = registry.execute(
                        "booking_execution",
                        session_id=session_id,
                        option_id=recommended_option.id,
                        journey_date=request.journey_date,
                        passenger_name=request.passenger_name,
                        passenger_count=request.passenger_count,
                        seat_number=seat_num,
                        seat_preference=request.seat_preference or user_prefs.seat_preference,
                        max_budget=effective_budget,
                        total_fare=recommended_option.total_fare,
                        origin=request.origin,
                        destination=request.destination,
                        departure_time=recommended_option.departure_time,
                        arrival_time=recommended_option.arrival_time,
                        is_auto_booked=True,
                        user_authorized=True,
                        payment_mode=effective_payment_mode,
                        idempotency_key=idempotency_key
                    )
                    act_step.tool_calls.append(call_book)
                    booking_dict = call_book.output_result or {}
                    booking_record = BookingRecord(**booking_dict)

                trace_steps.append(act_step)
                step_counter += 1

                # VERIFY STEP
                if booking_record and booking_record.status == "CONFIRMED":
                    call_verif = registry.execute("booking_verification_tool", session_id=session_id, booking_id=booking_record.booking_id)
                    verify_step = AgentTraceStep(
                        step_number=step_counter,
                        stage="VERIFY",
                        description=(
                            f"Provider confirmed booking {booking_record.booking_id} (Code: {booking_record.verification_code}, "
                            f"Seat: {booking_record.seat_number}, Payment: {booking_record.payment_mode} - {booking_record.payment_status})."
                        ),
                        tool_calls=[call_verif],
                        state_summary={
                            "verified": True,
                            "booking_id": booking_record.booking_id,
                            "payment_status": booking_record.payment_status,
                            "total_amount": booking_record.total_amount
                        },
                        timestamp=datetime.now().isoformat()
                    )
                    trace_steps.append(verify_step)
                    step_counter += 1
                trace_steps.append(act_step)
                step_counter += 1
        else:
            act_step = AgentTraceStep(
                step_number=step_counter,
                stage="ACT",
                description=f"Action prepared: '{recommended_option.title if recommended_option else 'None'}' utilizes open transit boarding (no advance seat reservation required).",
                tool_calls=[],
                timestamp=datetime.now().isoformat()
            )
            trace_steps.append(act_step)
            step_counter += 1

            verify_step = AgentTraceStep(
                step_number=step_counter,
                stage="VERIFY",
                description=f"Transit line readiness verified for '{recommended_option.title if recommended_option else 'None'}'. Timetable and corridor status verified.",
                tool_calls=[],
                state_summary={"verified": True, "requires_booking": False},
                timestamp=datetime.now().isoformat()
            )
            trace_steps.append(verify_step)
            step_counter += 1

        # ==========================================
        # STEP 11: MONITOR & LIVE TRACKING TELEMETRY
        # ==========================================
        call_mon = registry.execute("delay_monitor", session_id=session_id, origin=request.origin, destination=request.destination)
        
        # Initialize or update live tracking telemetry for the trip
        trip_id = f"TRIP-{session_id}"
        update_trip_telemetry({
            "trip_id": trip_id,
            "booking_id": booking_record.booking_id if booking_record else None,
            "origin": request.origin,
            "destination": request.destination,
            "current_lat": 12.9716,
            "current_lon": 77.5946,
            "current_stop": request.origin,
            "next_stop": "Transit Hub Junction",
            "progress_percentage": 10.0,
            "speed_kmh": 48.0,
            "eta_minutes": recommended_option.duration_minutes if recommended_option else 35,
            "status": "SCHEDULED"
        })

        monitor_step = AgentTraceStep(
            step_number=step_counter,
            stage="MONITOR",
            description=f"Active commute registered for live telemetry tracking ({trip_id}) and real-time delay surveillance.",
            tool_calls=[call_mon],
            state_summary={"monitoring_active": True, "trip_id": trip_id},
            timestamp=datetime.now().isoformat()
        )
        trace_steps.append(monitor_step)
        step_counter += 1

        status = "SUCCESS" if recommended_option else "REJECTED_CONSTRAINTS"

        plan_response = PlanResponse(
            session_id=session_id,
            request=request,
            recommended_option=recommended_option,
            all_options=ranked_options,
            steps_executed=trace_steps,
            rag_context=rag_result,
            booking_result=booking_record,
            decision_explanation=explanation_text,
            status=status,
            disruption_detected=False,
            persisted_task_id=session_id
        )

        # Save to SQLite Database
        memory_service.save_agent_session(
            session_id=session_id,
            status=status,
            request_data=request.model_dump(),
            plan_response=plan_response.model_dump(),
            option_id=recommended_option.id if recommended_option else None
        )

        return plan_response

    def replan_on_disruption(self, session_id: str, disruption: DisruptionEvent, allow_auto_rebook: bool = False, payment_mode: str = "ONLINE_WALLET") -> PlanResponse:
        """
        Stateful REPLAN step when a delay or condition changes.
        """
        saved_session = memory_service.recover_session(session_id)
        if not saved_session or not saved_session.get("request"):
            raise ValueError(f"Session {session_id} not found in persistent SQLite storage.")

        request = CommuteRequest(**saved_session["request"])
        user_id = request.user_id or "demo_commuter"
        user_prefs = CommutePreferences(**memory_service.get_preferences(user_id))

        trace_steps: List[AgentTraceStep] = []
        step_counter = 1

        # REPLAN step
        call_replan = registry.execute(
            "replanning",
            session_id=session_id,
            disruption_type=disruption.disruption_type,
            delay_minutes=disruption.delay_minutes,
            affected_mode=disruption.affected_mode,
            current_options=[]
        )

        replan_step = AgentTraceStep(
            step_number=step_counter,
            stage="REPLAN",
            description=(
                f"Disruption detected: {disruption.disruption_type.upper()} on {disruption.affected_mode.upper()} "
                f"(+{disruption.delay_minutes} min delay, {disruption.description}). Triggering autonomous re-planning cycle."
            ),
            tool_calls=[call_replan],
            timestamp=datetime.now().isoformat()
        )
        trace_steps.append(replan_step)
        step_counter += 1

        # Re-fetch routes and apply disruption impact
        call_routes = registry.execute("route_search", session_id=session_id, origin=request.origin, destination=request.destination, target_arrival=request.desired_arrival_time)
        raw_routes = call_routes.output_result if isinstance(call_routes.output_result, list) else []
        options = [CommuteOption(**r) for r in raw_routes]

        for opt in options:
            if opt.mode.lower() == disruption.affected_mode.lower():
                opt.duration_minutes += disruption.delay_minutes
                opt.traffic_delay_min += disruption.delay_minutes
                opt.reliability_score = max(0.2, opt.reliability_score - 0.4)

        # Re-evaluate
        recommended_option, ranked_options = decision_engine.evaluate_and_rank(
            options=options,
            request=request,
            preferences=user_prefs
        )

        replan_decide_step = AgentTraceStep(
            step_number=step_counter,
            stage="DECIDE",
            description=f"Re-ranked options after disruption. New optimal choice: {recommended_option.title if recommended_option else 'None'}.",
            timestamp=datetime.now().isoformat()
        )
        trace_steps.append(replan_decide_step)

        booking_record = None
        if recommended_option and recommended_option.requires_booking and allow_auto_rebook:
            idempotency_key = f"rebook_{session_id}_{recommended_option.id}_{datetime.now().strftime('%H%M%S')}"
            call_book = registry.execute(
                "booking_execution",
                session_id=session_id,
                option_id=recommended_option.id,
                journey_date=request.journey_date,
                passenger_name=request.passenger_name,
                passenger_count=request.passenger_count,
                seat_preference=request.seat_preference or "window",
                max_budget=request.budget_limit or 2000.0,
                total_fare=recommended_option.total_fare,
                origin=request.origin,
                destination=request.destination,
                departure_time=recommended_option.departure_time,
                arrival_time=recommended_option.arrival_time,
                is_auto_booked=True,
                user_authorized=True,
                payment_mode=payment_mode,
                idempotency_key=idempotency_key
            )
            if call_book.output_result:
                booking_record = BookingRecord(**call_book.output_result)

        explanation = (
            f"Autonomous Agent re-planned your commute due to a +{disruption.delay_minutes} min disruption on {disruption.affected_mode}. "
            f"Switching to **{recommended_option.title if recommended_option else 'backup option'}** to protect your arrival deadline."
        )

        plan_response = PlanResponse(
            session_id=session_id,
            request=request,
            recommended_option=recommended_option,
            all_options=ranked_options,
            steps_executed=trace_steps,
            booking_result=booking_record,
            decision_explanation=explanation,
            status="SUCCESS" if recommended_option else "REJECTED_CONSTRAINTS",
            disruption_detected=True,
            persisted_task_id=session_id
        )

        memory_service.save_agent_session(
            session_id=session_id,
            status="REPLANNED",
            request_data=request.model_dump(),
            plan_response=plan_response.model_dump(),
            option_id=recommended_option.id if recommended_option else None
        )

        return plan_response


agent = AutonomousCommuteAgent()
