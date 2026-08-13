"""Pydantic schemas for all Claude outputs and internal data flow."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Input ────────────────────────────────────────────────────────────────────

class SopInput(BaseModel):
    text: str
    client_name: str = ""
    process_name: str = ""
    source_url: str = ""


# ── Task 1: Process Redesign ──────────────────────────────────────────────────

class Step(BaseModel):
    step_number: int
    title: str
    description: str
    owner: str = ""
    estimated_time_minutes: Optional[int] = None
    pain_points: list[str] = Field(default_factory=list)


class RedesignResult(BaseModel):
    process_name: str
    current_state_summary: str
    optimised_steps: list[Step]
    estimated_time_saving_percent: Optional[float] = None
    key_improvements: list[str] = Field(default_factory=list)


# ── Task 2: Automation Map ────────────────────────────────────────────────────

class AutomationOpportunity(BaseModel):
    opportunity_id: str
    title: str
    description: str
    tool_suggestion: str = ""
    hours_saved_per_week: Optional[float] = None
    implementation_effort: int = Field(ge=1, le=10)
    error_reduction_score: int = Field(ge=1, le=10)
    revenue_impact_score: int = Field(ge=1, le=10)

    @property
    def composite_score(self) -> float:
        """Weighted score per spec §11: hours 40%, effort 25%, error 20%, revenue 15%."""
        hours_norm = min((self.hours_saved_per_week or 0) / 40.0, 1.0) * 10
        effort_inv = 11 - self.implementation_effort  # lower effort = higher score
        return (
            hours_norm * 0.40
            + effort_inv * 0.25
            + self.error_reduction_score * 0.20
            + self.revenue_impact_score * 0.15
        )


class AutomationMap(BaseModel):
    opportunities: list[AutomationOpportunity]
    priority_order: list[str] = Field(default_factory=list, description="opportunity_ids in priority order")


# ── Task 3: Flowchart ─────────────────────────────────────────────────────────

class FlowchartResult(BaseModel):
    dot_source: str  # Graphviz DOT language string


# ── Task 4: Executive Summary ─────────────────────────────────────────────────

class SummaryResult(BaseModel):
    executive_summary: str


# ── Cross-Process (multi-SOP mode) ────────────────────────────────────────────

class CrossProcessResult(BaseModel):
    insights: str
    shared_bottlenecks: list[str] = Field(default_factory=list)
    cross_automation_opportunities: list[str] = Field(default_factory=list)


# ── Full run result ───────────────────────────────────────────────────────────

class SingleSopResult(BaseModel):
    sop_input: SopInput
    redesign: RedesignResult
    automation_map: AutomationMap
    flowchart: FlowchartResult
    executive_summary: str


class RunResult(BaseModel):
    sop_results: list[SingleSopResult]
    cross_process: Optional[CrossProcessResult] = None
    executive_summary: str  # top-level summary (last SOP or cross-process)
