import pytest
from backend.schemas import CommuteOption, CommuteRequest, CommutePreferences
from backend.decision_engine import decision_engine


def get_sample_options():
    return [
        CommuteOption(
            id="opt_metro",
            mode="metro",
            title="Metro Line",
            origin="A",
            destination="B",
            departure_time="08:15",
            arrival_time="09:00",
            duration_minutes=45,
            base_fare=3.0,
            total_fare=3.0,
            reliability_score=0.90
        ),
        CommuteOption(
            id="opt_train",
            mode="express_train",
            title="Express Train",
            origin="A",
            destination="B",
            departure_time="08:30",
            arrival_time="09:00",
            duration_minutes=30,
            base_fare=12.0,
            total_fare=12.0,
            reliability_score=0.98,
            requires_booking=True
        ),
        CommuteOption(
            id="opt_rideshare",
            mode="rideshare",
            title="Rideshare",
            origin="A",
            destination="B",
            departure_time="08:38",
            arrival_time="09:00",
            duration_minutes=22,
            base_fare=28.0,
            total_fare=28.0,
            reliability_score=0.85
        )
    ]


def test_cheapest_strategy():
    req = CommuteRequest(origin="A", destination="B", budget_limit=50.0, desired_arrival_time="09:00", ranking_strategy="cheapest")
    rec, ranked = decision_engine.evaluate_and_rank(get_sample_options(), req)
    assert rec is not None
    assert rec.mode == "metro"  # Lowest fare


def test_fastest_strategy():
    req = CommuteRequest(origin="A", destination="B", budget_limit=50.0, desired_arrival_time="09:00", ranking_strategy="fastest")
    rec, ranked = decision_engine.evaluate_and_rank(get_sample_options(), req)
    assert rec is not None
    assert rec.mode == "rideshare"  # 22 minutes


def test_hard_budget_constraint_filter():
    # Budget of $5 only allows metro ($3). Train ($12) and Rideshare ($28) must be rejected
    req = CommuteRequest(origin="A", destination="B", budget_limit=5.0, desired_arrival_time="09:00")
    rec, ranked = decision_engine.evaluate_and_rank(get_sample_options(), req)
    assert rec.mode == "metro"
    for r in ranked:
        if r.total_fare > 5.0:
            assert r.is_eligible is False
            assert len(r.rejection_reasons) > 0


def test_hard_deadline_constraint_filter():
    opts = get_sample_options()
    # Modify metro to arrive late at 09:15 when desired arrival is 09:00
    opts[0].arrival_time = "09:15"
    req = CommuteRequest(origin="A", destination="B", budget_limit=50.0, desired_arrival_time="09:00")
    rec, ranked = decision_engine.evaluate_and_rank(opts, req)
    
    metro_opt = [o for o in ranked if o.mode == "metro"][0]
    assert metro_opt.is_eligible is False
    assert any("deadline" in r.lower() or "past" in r.lower() for r in metro_opt.rejection_reasons)
