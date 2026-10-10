from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from backend.schemas import CommuteOption, CommuteRequest, CommutePreferences


class DecisionEngine:
    """
    Deterministic Decision Engine:
    - Enforces hard constraints (budget, deadline, reliability threshold)
    - Multi-strategy option ranking (cheapest, fastest, balanced, preference)
    - Generates actionable rejection explanations for excluded routes
    """

    def evaluate_and_rank(
        self,
        options: List[CommuteOption],
        request: CommuteRequest,
        preferences: Optional[CommutePreferences] = None
    ) -> Tuple[Optional[CommuteOption], List[CommuteOption]]:
        budget_limit = request.budget_limit if request.budget_limit is not None else (preferences.max_budget if preferences else 2000.0)
        desired_arrival = request.desired_arrival_time or (preferences.latest_arrival_time if preferences else "09:00")
        strategy = (request.ranking_strategy or (preferences.ranking_strategy if preferences else "balanced")).lower()
        preferred_modes = preferences.preferred_modes if preferences else ["metro", "express_train", "bus", "rideshare"]

        evaluated_options: List[CommuteOption] = []

        for opt in options:
            reasons = []
            is_eligible = True

            # 1. Hard Budget Constraint
            if opt.total_fare > budget_limit:
                is_eligible = False
                reasons.append(f"Total fare ₹{opt.total_fare:.2f} exceeds budget limit of ₹{budget_limit:.2f}")


            # 2. Hard Deadline Constraint
            try:
                opt_arr = datetime.strptime(opt.arrival_time, "%H:%M")
                dl_arr = datetime.strptime(desired_arrival, "%H:%M")
                if opt_arr > dl_arr:
                    is_eligible = False
                    mins_late = int((opt_arr - dl_arr).total_seconds() / 60)
                    reasons.append(f"Arrival time {opt.arrival_time} is {mins_late} min past deadline {desired_arrival}")
            except Exception:
                pass

            # 3. Mode preference filter (if specific list enforced)
            if preferred_modes and opt.mode.lower() not in [m.lower() for m in preferred_modes]:
                # Soft penalty rather than rejection unless empty
                reasons.append(f"Mode '{opt.mode}' is outside user preferred modes list")

            opt.is_eligible = is_eligible
            opt.rejection_reasons = reasons

            # Compute Score
            opt.score = self._compute_score(opt, strategy, budget_limit, preferred_modes)
            evaluated_options.append(opt)

        # Sort eligible options first by score, then non-eligible
        eligible = [o for o in evaluated_options if o.is_eligible]
        ineligible = [o for o in evaluated_options if not o.is_eligible]

        eligible.sort(key=lambda x: x.score, reverse=True)
        ineligible.sort(key=lambda x: x.score, reverse=True)

        all_ranked = eligible + ineligible
        recommended = eligible[0] if eligible else None

        return recommended, all_ranked

    def _compute_score(self, opt: CommuteOption, strategy: str, max_budget: float, preferred_modes: List[str]) -> float:
        # Normalize fare score (0 to 1, lower fare = higher score)
        fare_ratio = max(0.0, 1.0 - (opt.total_fare / max(max_budget * 1.5, 30.0)))
        
        # Normalize duration score (0 to 1, faster = higher score)
        time_ratio = max(0.0, 1.0 - (opt.duration_minutes / 90.0))

        # Reliability score
        reliability = opt.reliability_score

        # Preference boost
        pref_boost = 0.2 if opt.mode.lower() in [m.lower() for m in preferred_modes] else 0.0

        if strategy == "cheapest":
            score = (fare_ratio * 0.70) + (time_ratio * 0.15) + (reliability * 0.15) + pref_boost
        elif strategy == "fastest":
            score = (time_ratio * 0.70) + (fare_ratio * 0.15) + (reliability * 0.15) + pref_boost
        elif strategy == "preference":
            score = (pref_boost * 0.40) + (reliability * 0.30) + (time_ratio * 0.15) + (fare_ratio * 0.15)
        else:  # balanced
            score = (time_ratio * 0.35) + (fare_ratio * 0.35) + (reliability * 0.30) + pref_boost

        return round(float(score), 4)


decision_engine = DecisionEngine()
