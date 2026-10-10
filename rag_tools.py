from typing import Dict, Any
from backend.tools.registry import registry
from backend.rag_service import rag_service


@registry.register(
    name="rag_retrieval",
    description="Retrieve relevant transit policies, discount rules, luggage guidelines, and disruption protocols from the local knowledge base."
)
def rag_retrieval(query: str, top_k: int = 3) -> Dict[str, Any]:
    result = rag_service.query(query, top_k=top_k)
    return result.model_dump()
