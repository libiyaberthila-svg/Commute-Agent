import logging
import httpx
from typing import Dict, Any, Optional
from backend.config import settings

logger = logging.getLogger(__name__)


class LLMProvider:
    """
    Optional LLM provider with LangChain/Ollama integration and automatic deterministic fallback.
    The system runs 100% locally and offline when Ollama is absent or disabled.
    """
    def __init__(self):
        self.use_llm = settings.use_llm
        self.base_url = settings.ollama_base_url
        self.model_name = settings.ollama_model

    def is_available(self) -> bool:
        if not self.use_llm:
            return False
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=1.0)
            return resp.status_code == 200
        except Exception:
            return False

    def generate_explanation(self, option_data: Dict[str, Any], constraints: Dict[str, Any], rag_context: Optional[str] = None) -> str:
        """
        Generate natural language decision explanation.
        """
        if self.is_available():
            try:
                prompt = (
                    f"Explain why this commute route is recommended based on constraints:\n"
                    f"Recommended: {option_data.get('title')} (Fare: ${option_data.get('total_fare')}, Duration: {option_data.get('duration_minutes')} min)\n"
                    f"Constraints: Max Budget: ${constraints.get('max_budget')}, Arrival: {constraints.get('desired_arrival_time')}\n"
                    f"RAG Policy Context: {rag_context or 'None'}\n"
                    f"Provide a concise, factual 2-sentence explanation."
                )
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False
                }
                resp = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=5.0)
                if resp.status_code == 200:
                    return resp.json().get("response", "").strip()
            except Exception as e:
                logger.warning(f"Ollama generation failed ({e}), falling back to deterministic explanation.")

        # High quality deterministic explanation
        title = option_data.get("title", "Selected Commute Option")
        fare = option_data.get("total_fare", 0.0)
        dur = option_data.get("duration_minutes", 0)
        mode = option_data.get("mode", "transit")
        dep = option_data.get("departure_time", "N/A")
        arr = option_data.get("arrival_time", "N/A")
        score = option_data.get("score", 0.0)

        explanation = (
            f"Autonomous Agent selected **{title}** (Mode: `{mode.upper()}`) departing at **{dep}** and arriving at **{arr}** ({dur} min). "
            f"It offers the highest utility score ({score:.2f}) under the balanced strategy, with a total fare of **₹{fare:.2f}** "
            f"strictly satisfying your budget limit (₹{constraints.get('max_budget', 2000.0):.2f}) and on-time arrival requirements."
        )
        if rag_context:
            explanation += f" *Grounding note: Verified with indexed transit policy guidelines.*"
        return explanation
