import pytest
from backend.tools.registry import registry
from backend.database import init_db

# Ensure all tools registered
import backend.tools.travel_tools
import backend.tools.constraint_tools
import backend.tools.booking_tools
import backend.tools.rag_tools
import backend.tools.memory_tools
import backend.tools.monitor_tools
import backend.tools.wallet_and_payment_tools


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_registry_has_all_required_tools():
    tool_names = [t["name"] for t in registry.list_tools()]
    required = [
        "route_search", "weather", "traffic_status", "transport_search",
        "travel_time", "fare_comparison", "budget_check", "deadline_check",
        "departure_time", "alternative_route",
        "seat_availability", "seat_selection", "booking_eligibility",
        "booking_execution", "booking_verification", "booking_status", "booking_recovery",
        "rag_retrieval", "user_preferences", "commute_history",
        "delay_monitor", "replanning", "notification", "decision_explanation",
        "demo_account_tool", "wallet_balance_tool", "wallet_topup_tool",
        "seat_availability_tool", "seat_selection_tool", "fare_validation_tool",
        "payment_method_tool", "demo_wallet_payment_tool", "offline_payment_tool",
        "transaction_verification_tool", "booking_verification_tool", "payment_reconciliation_tool"
    ]
    for req in required:
        assert req in tool_names, f"Missing required tool: {req}"



def test_travel_tools_execution():
    res_route = registry.execute("route_search", origin="North Station", destination="Financial District", target_arrival="09:00")
    assert res_route.status == "SUCCESS"
    assert len(res_route.output_result) >= 3

    res_weather = registry.execute("weather", location="North Station")
    assert res_weather.status == "SUCCESS"
    assert "temperature_c" in res_weather.output_result

    res_traffic = registry.execute("traffic_status", origin="North Station", destination="Financial District")
    assert res_traffic.status == "SUCCESS"
    assert "congestion_level" in res_traffic.output_result

    res_tt = registry.execute("travel_time", origin="North Station", destination="Financial District", mode="express_train")
    assert res_tt.status == "SUCCESS"
    assert res_tt.output_result["total_duration_min"] > 0

    res_fc = registry.execute("fare_comparison", origin="North Station", destination="Financial District")
    assert res_fc.status == "SUCCESS"
    assert len(res_fc.output_result) > 0


def test_constraint_tools_execution():
    # Budget check passes when within budget
    res_b_pass = registry.execute("budget_check", fare=15.0, max_budget=25.0)
    assert res_b_pass.output_result["is_within_budget"] is True
    assert res_b_pass.output_result["remaining_budget"] == 10.0

    # Budget check fails when exceeding
    res_b_fail = registry.execute("budget_check", fare=35.0, max_budget=25.0)
    assert res_b_fail.output_result["is_within_budget"] is False

    # Deadline check
    res_d_pass = registry.execute("deadline_check", estimated_arrival="08:45", deadline_time="09:00")
    assert res_d_pass.output_result["is_on_time"] is True

    res_d_fail = registry.execute("deadline_check", estimated_arrival="09:15", deadline_time="09:00")
    assert res_d_fail.output_result["is_on_time"] is False


def test_booking_tools_execution():
    # Seat availability
    res_avail = registry.execute("seat_availability", option_id="opt_train_exp_101")
    assert res_avail.status == "SUCCESS"
    assert len(res_avail.output_result) > 0

    # Seat selection
    res_sel = registry.execute("seat_selection", option_id="opt_train_exp_101", preference="window")
    assert res_sel.status == "SUCCESS"
    assert res_sel.output_result["selected"] is True

    # Booking eligibility
    res_elig = registry.execute(
        "booking_eligibility",
        requires_booking=True,
        available_seats=5,
        total_fare=15.0,
        max_auto_budget=20.0,
        user_authorized=True
    )
    assert res_elig.output_result["is_eligible_for_auto_booking"] is True
