import pytest
from pathlib import Path
from backend.rag_service import rag_service
from backend.config import KNOWLEDGE_BASE_DIR


def test_rag_query_groundedness():
    # Query something present in the seeded policy
    res = rag_service.query("What is the peak hours fare and refund policy for delays?")
    assert res.rag_used is True
    assert len(res.sources) > 0
    assert res.confidence_score > 0.0
    assert any("refund" in s["excerpt"].lower() or "peak" in s["excerpt"].lower() for s in res.sources)


def test_rag_ingest_and_query_custom_file(tmp_path):
    test_file = tmp_path / "office_commute_rules.txt"
    test_file.write_text(
        "SPECIAL SUBWAY SHUTTLE INFO:\n"
        "Shuttle 88 runs exclusively between Tech Park and Central Station every 10 minutes.\n"
        "Bicycles are free of charge on this specific shuttle.\n",
        encoding="utf-8"
    )

    ingest_res = rag_service.ingest_file(str(test_file))
    assert ingest_res["status"] == "INGESTED"
    assert ingest_res["chunk_count"] >= 1

    query_res = rag_service.query("Are bicycles allowed on Shuttle 88?")
    assert query_res.rag_used is True
    assert any("Tech Park" in s["excerpt"] for s in query_res.sources)
