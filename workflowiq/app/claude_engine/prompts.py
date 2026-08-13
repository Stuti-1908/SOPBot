"""System and user prompt templates for all 4 WorkflowIQ tasks + cross-process."""

SYSTEM_BASE = """You are WorkflowIQ, an expert business process analyst at DadaAI.
Your outputs are used directly in professional client reports.
Always respond with valid JSON matching the exact schema requested.
Do not include markdown fences, commentary, or any text outside the JSON object.
Never use em dashes (—) or en dashes (–) anywhere in your output; use a plain
hyphen (-) or rewrite the sentence instead."""


TASK1_REDESIGN = """\
Analyse the following Standard Operating Procedure (SOP) and return a JSON object matching this schema:

{{
  "process_name": "string",
  "current_state_summary": "string (2-4 sentences)",
  "optimised_steps": [
    {{
      "step_number": int,
      "title": "string",
      "description": "string",
      "owner": "string",
      "estimated_time_minutes": int | null,
      "pain_points": ["string"]
    }}
  ],
  "estimated_time_saving_percent": float | null,
  "key_improvements": ["string"]
}}

SOP TEXT:
{sop_text}
"""

TASK2_AUTOMATION = """\
Given the SOP and the redesigned process below, identify automation opportunities.
Return a JSON object matching this schema:

{{
  "opportunities": [
    {{
      "opportunity_id": "string (e.g. OPP-001)",
      "title": "string",
      "description": "string",
      "tool_suggestion": "string",
      "hours_saved_per_week": float | null,
      "implementation_effort": int (1=trivial, 10=major project),
      "error_reduction_score": int (1-10),
      "revenue_impact_score": int (1-10)
    }}
  ],
  "priority_order": ["opportunity_id strings in priority order"]
}}

SOP TEXT:
{sop_text}

REDESIGNED PROCESS:
{redesign_json}
"""

TASK3_FLOWCHART = """\
Generate a Graphviz DOT language flowchart for the optimised process below.
Return a JSON object with a single key "dot_source" containing the DOT string.
The flowchart should be clear, professional, and use rankdir=TB (top to bottom,
vertical) so it reads well on a tall printed page.

{{
  "dot_source": "digraph {{ ... }}"
}}

REDESIGNED PROCESS:
{redesign_json}
"""

TASK4_SUMMARY = """\
Write a professional executive summary for the following process analysis.
Target audience: business owner / operations manager.
Length: 3-5 paragraphs. Include key wins, automation ROI potential, and recommended next steps.
Return a JSON object:

{{
  "executive_summary": "string (markdown supported)"
}}

REDESIGNED PROCESS:
{redesign_json}

AUTOMATION OPPORTUNITIES:
{automation_json}
"""

CROSS_PROCESS = """\
You have been given {n} SOPs from the same client. Identify cross-process patterns,
shared bottlenecks, and automation opportunities that span multiple processes.
Return a JSON object:

{{
  "insights": "string (markdown, 3-5 paragraphs)",
  "shared_bottlenecks": ["string"],
  "cross_automation_opportunities": ["string"]
}}

LABELLED SOPs:
{labeled_sops_json}
"""
