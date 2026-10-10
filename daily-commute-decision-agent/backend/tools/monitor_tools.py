from typing import Dict, Any, List, Optional
from backend.tools.registry import registry
from backend.providers.mock_weather import MockWeatherTrafficProvider
from backend.providers.llm_provider import LLMProvider

weather_traffic = MockWeatherTrafficProvider()
llm_provider = LLMProvider()


@registry.register(
    name="delay_monitor",
    description="Check for active delay alerts, road accidents, rail maintenance, or weather storms on a route."
)
def delay_monitor(origin: str, destination: str, mode: str = "all") -> Dict[str, Any]:
    traffic = weather_traffic.get_traffic_status(origin, destination)
    weather_info = weather_traffic.get_weather(origin)

    has_delay = traffic.get("delay_minutes", 0) > 10 or weather_info.get("precipitation_chance", 0) > 60
    advisory = "Normal commute conditions."
    if has_delay:
        advisory = f"Alert: High congestion or adverse weather detected. Expected delay: +{traffic.get('delay_minutes', 0)} min."

    return {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "is_disrupted": has_delay,
        "traffic_delay_min": traffic.get("delay_minutes", 0),
        "congestion": traffic.get("congestion_level", "Normal"),
        "weather_condition": weather_info.get("condition", "Clear"),
        "advisory": advisory
    }


@registry.register(
    name="replanning",
    description="Trigger an autonomous re-planning cycle when a disruption or delay invalidates the active commute plan."
)
def replanning(
    session_id: str,
    disruption_type: str,
    delay_minutes: int,
    affected_mode: str,
    current_options: List[Dict[str, Any]]
) -> Dict[str, Any]:
    recalculated = []
    for opt in current_options:
        opt_copy = dict(opt)
        if opt_copy.get("mode") == affected_mode:
            opt_copy["duration_minutes"] = opt_copy.get("duration_minutes", 30) + delay_minutes
            opt_copy["traffic_delay_min"] = opt_copy.get("traffic_delay_min", 0) + delay_minutes
            opt_copy["reliability_score"] = max(0.2, opt_copy.get("reliability_score", 0.9) - 0.35)
            opt_copy["rejection_reasons"] = [f"Disrupted by {disruption_type} (+{delay_minutes} min delay)"]
        recalculated.append(opt_copy)

    return {
        "session_id": session_id,
        "status": "REPLANNED",
        "affected_mode": affected_mode,
        "delay_minutes": delay_minutes,
        "recalculated_options": recalculated,
        "action_required": "Select best non-disrupted alternative."
    }


@registry.register(
    name="notification",
    description="Dispatch proactive commute notifications or booking confirmation alerts to the user interface."
)
def notification(title: str, message: str, level: str = "INFO") -> Dict[str, Any]:
    return {
        "sent": True,
        "channel": "ui_banner",
        "level": level,
        "title": title,
        "message": message
    }


@registry.register(
    name="decision_explanation",
    description="Generate human-interpretable rationale for why the agent selected a specific route and discarded others."
)
def decision_explanation(
    selected_option: Dict[str, Any],
    budget_limit: float,
    desired_arrival: str,
    rag_context: Optional[str] = None
) -> Dict[str, Any]:
    text = llm_provider.generate_explanation(
        option_data=selected_option,
        constraints={"max_budget": budget_limit, "desired_arrival_time": desired_arrival},
        rag_context=rag_context
    )
    return {
        "explanation": text,
        "selected_option_id": selected_option.get("id"),
        "confidence_score": selected_option.get("score", 0.95)
    }
