"""Integration tests for Claude engine with mocked API responses."""
import json
import pytest
from unittest.mock import patch, MagicMock

from app.schemas import SopInput
from app.claude_engine import engine


MOCK_REDESIGN = {
    "process_name": "Invoice Processing",
    "current_state_summary": "Manual AP process with many pain points.",
    "optimised_steps": [
        {"step_number": 1, "title": "Auto-capture", "description": "OCR", "owner": "AP Clerk",
         "estimated_time_minutes": 2, "pain_points": ["Manual entry errors"]}
    ],
    "estimated_time_saving_percent": 45.0,
    "key_improvements": ["OCR", "Auto-approval routing"],
}

MOCK_AUTOMATION = {
    "opportunities": [
        {
            "opportunity_id": "OPP-001",
            "title": "OCR Invoice Capture",
            "description": "Automate data entry",
            "tool_suggestion": "Google Document AI",
            "hours_saved_per_week": 8.0,
            "implementation_effort": 4,
            "error_reduction_score": 9,
            "revenue_impact_score": 6,
        }
    ],
    "priority_order": ["OPP-001"],
}

MOCK_FLOWCHART = {"dot_source": "digraph { A -> B -> C }"}

MOCK_SUMMARY = {"executive_summary": "Significant improvements are achievable."}


def _mock_call(prompt: str, max_tokens: int = 4096) -> dict:
    """Route to the right mock response based on prompt content.

    Order matters here: later prompts embed earlier tasks' JSON output
    (e.g. TASK2_AUTOMATION includes {redesign_json}, so its prompt text
    also contains "optimised_steps"). Check the most specific/exclusive
    markers first so a prompt that echoes a prior task's output doesn't
    get misrouted to that prior task's mock response.
    """
    if "shared_bottlenecks" in prompt:
        return {
            "insights": "Cross-process insight text.",
            "shared_bottlenecks": ["Manual data entry"],
            "cross_automation_opportunities": ["Unified OCR platform"],
        }
    elif "executive_summary" in prompt:
        # TASK4_SUMMARY embeds both redesign_json (optimised_steps) and
        # automation_json (opportunity_id), so it must be checked before
        # either of those markers.
        return MOCK_SUMMARY
    elif "dot_source" in prompt:
        return MOCK_FLOWCHART
    elif "opportunity_id" in prompt:
        # TASK2_AUTOMATION embeds redesign_json (optimised_steps) too,
        # so this must be checked before "optimised_steps".
        return MOCK_AUTOMATION
    elif "optimised_steps" in prompt:
        return MOCK_REDESIGN
    return {}


@patch.object(engine, "_call", side_effect=_mock_call)
def test_run_analysis_single_sop(mock_call):
    sop = SopInput(text="Invoice SOP text here.", client_name="Acme", process_name="Invoice Processing")
    result = engine.run_analysis([sop])
    assert len(result.sop_results) == 1
    assert result.cross_process is None
    assert result.sop_results[0].redesign.process_name == "Invoice Processing"
    assert len(result.sop_results[0].automation_map.opportunities) == 1


@patch.object(engine, "_call", side_effect=_mock_call)
def test_run_analysis_multi_sop_triggers_cross_process(mock_call):
    sops = [
        SopInput(text="SOP 1 text.", client_name="Acme", process_name="Invoice Processing"),
        SopInput(text="SOP 2 text.", client_name="Acme", process_name="HR Onboarding"),
    ]
    result = engine.run_analysis(sops)
    assert len(result.sop_results) == 2
    assert result.cross_process is not None
    assert "Cross-process" in result.cross_process.insights or len(result.cross_process.insights) > 0
