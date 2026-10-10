import pytest
import uuid
from backend.database import init_db
from backend.schemas import CommuteRequest, DisruptionEvent
from backend.agent import agent





def test_agent_full_workflow_execution():
    session_id = f"test_wf_{uuid.uuid4().hex[:6]}"
    req = CommuteRequest(
        origin="North Station",
        destination="Financial District",
        journey_date="2026-10-10",
        desired_arrival_time="09:00",
        budget_limit=500.0,
        passenger_name="Jane Agent",
        passenger_count=1,
        seat_preference="window",
        ranking_strategy="balanced",
        auto_book=True,
        auto_book_authorized=True
    )

    response = agent.run_workflow(req, session_id=session_id)
    assert response.status == "SUCCESS"
    assert response.recommended_option is not None
    assert len(response.all_options) >= 3
    assert len(response.steps_executed) >= 10  # All stages executed

    # Check stage sequence in trace
    stages = [s.stage for s in response.steps_executed]
    assert "UNDERSTAND" in stages
    assert "PLAN" in stages
    assert "SELECT_TOOLS" in stages
    assert "EXECUTE" in stages
    assert "OBSERVE" in stages
    assert "RETRIEVE_RAG" in stages
    assert "EVALUATE" in stages
    assert "DECIDE" in stages
    assert "MONITOR" in stages

    # Check that tool calls were executed and recorded
    all_tool_calls = []
    for step in response.steps_executed:
        all_tool_calls.extend(step.tool_calls)
    assert len(all_tool_calls) > 0


def test_agent_disruption_replanning():
    session_id = f"test_replan_{uuid.uuid4().hex[:6]}"
    req = CommuteRequest(
        origin="North Station",
        destination="Financial District",
        journey_date="2026-10-10",
        desired_arrival_time="09:00",
        budget_limit=500.0,
        passenger_name="Replan Commuter",
        auto_book=False,
        auto_book_authorized=False
    )


    # Initial plan
    initial_res = agent.run_workflow(req, session_id=session_id)
    assert initial_res.status == "SUCCESS"

    # Simulate disruption on train
    disruption = DisruptionEvent(
        disruption_type="signal_failure",
        severity="severe",
        affected_mode="express_train",
        delay_minutes=40,
        location="North Rail Bridge",
        description="Track signal failure causing 40 min delays on express trains."
    )

    replan_res = agent.replan_on_disruption(session_id=session_id, disruption=disruption)
    assert replan_res.disruption_detected is True
    assert replan_res.recommended_option is not None
    # Train should have been penalized / dropped in favor of reliable Metro or Rideshare
    assert replan_res.recommended_option.mode != "express_train" or replan_res.recommended_option.duration_minutes > 50
