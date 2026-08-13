"""Unit tests for Pydantic schema validation."""
import pytest
from app.schemas import (
    RedesignResult, AutomationMap, AutomationOpportunity,
    FlowchartResult, RunResult, SingleSopResult, SopInput,
)


def make_redesign() -> RedesignResult:
    return RedesignResult(
        process_name="Invoice Processing",
        current_state_summary="Manual, error-prone AP process.",
        optimised_steps=[
            {"step_number": 1, "title": "Auto-capture invoices", "description": "Use OCR", "owner": "AP Clerk"}
        ],
        estimated_time_saving_percent=40.0,
        key_improvements=["OCR extraction", "Automated approval routing"],
    )


def make_automation_map() -> AutomationMap:
    return AutomationMap(
        opportunities=[
            AutomationOpportunity(
                opportunity_id="OPP-001",
                title="OCR Invoice Capture",
                description="Automate data entry with OCR",
                tool_suggestion="Google Document AI",
                hours_saved_per_week=8.0,
                implementation_effort=4,
                error_reduction_score=9,
                revenue_impact_score=6,
            )
        ],
        priority_order=["OPP-001"],
    )


def test_redesign_valid():
    r = make_redesign()
    assert r.process_name == "Invoice Processing"
    assert len(r.optimised_steps) == 1


def test_automation_composite_score():
    opp = AutomationOpportunity(
        opportunity_id="OPP-001",
        title="Test",
        description="Test opp",
        hours_saved_per_week=20.0,
        implementation_effort=3,
        error_reduction_score=8,
        revenue_impact_score=7,
    )
    score = opp.composite_score
    assert 0 < score <= 10


def test_automation_effort_bounds():
    with pytest.raises(Exception):
        AutomationOpportunity(
            opportunity_id="OPP-X",
            title="Bad",
            description="Bad",
            implementation_effort=11,  # out of range
            error_reduction_score=5,
            revenue_impact_score=5,
        )


def test_flowchart_schema():
    f = FlowchartResult(dot_source='digraph { A -> B }')
    assert "digraph" in f.dot_source


def test_run_result_assembles():
    sop = SopInput(text="SOP text", client_name="Acme")
    redesign = make_redesign()
    automation = make_automation_map()
    flowchart = FlowchartResult(dot_source="digraph { A -> B }")
    sr = SingleSopResult(
        sop_input=sop,
        redesign=redesign,
        automation_map=automation,
        flowchart=flowchart,
        executive_summary="Great improvements possible.",
    )
    result = RunResult(
        sop_results=[sr],
        executive_summary="Great improvements possible.",
    )
    assert len(result.sop_results) == 1
    assert result.cross_process is None
