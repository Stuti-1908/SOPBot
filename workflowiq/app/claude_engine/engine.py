"""Claude API calls for all 4 WorkflowIQ tasks."""
from __future__ import annotations
import json
import os
import anthropic

from app.schemas import (
    SopInput, RunResult, SingleSopResult,
    RedesignResult, AutomationMap, FlowchartResult, CrossProcessResult,
)
from app.claude_engine.prompts import (
    SYSTEM_BASE, TASK1_REDESIGN, TASK2_AUTOMATION,
    TASK3_FLOWCHART, TASK4_SUMMARY, CROSS_PROCESS,
)

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 4096

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _extract_json_object(text: str) -> str:
    """Find the first '{' and its balanced matching '}', ignoring surrounding prose/fences."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no '{' found in Claude response")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("no balanced closing '}' found in Claude response")


def _call(prompt: str, max_tokens: int = MAX_TOKENS) -> dict:
    """Single Claude call; returns parsed JSON dict.

    Claude is instructed to return pure JSON but occasionally prefixes it with
    prose commentary (confirmed to happen on this same model/prompt style in
    SOPBot's transcript extraction). Fall back to locating the JSON object by
    brace-matching rather than trusting json.loads on the raw text alone.
    """
    msg = _client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_BASE,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()

    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as first_err:
        try:
            return json.loads(_extract_json_object(raw))
        except (ValueError, json.JSONDecodeError) as second_err:
            raise ValueError(
                f"Claude returned invalid JSON: {first_err} | extraction attempt: {second_err} | raw[:500]={raw[:500]!r}"
            ) from second_err


def run_task1_redesign(sop_text: str) -> RedesignResult:
    data = _call(TASK1_REDESIGN.format(sop_text=sop_text))
    return RedesignResult.model_validate(data)


def run_task2_automation(sop_text: str, redesign: RedesignResult) -> AutomationMap:
    data = _call(TASK2_AUTOMATION.format(
        sop_text=sop_text,
        redesign_json=redesign.model_dump_json(indent=2),
    ))
    return AutomationMap.model_validate(data)


def run_task3_flowchart(redesign: RedesignResult) -> FlowchartResult:
    data = _call(TASK3_FLOWCHART.format(
        redesign_json=redesign.model_dump_json(indent=2),
    ))
    return FlowchartResult.model_validate(data)


def run_task4_summary(redesign: RedesignResult, automation: AutomationMap) -> str:
    data = _call(TASK4_SUMMARY.format(
        redesign_json=redesign.model_dump_json(indent=2),
        automation_json=automation.model_dump_json(indent=2),
    ), max_tokens=2048)
    return data["executive_summary"]


def run_cross_process(labeled_sops: list[dict]) -> CrossProcessResult:
    data = _call(CROSS_PROCESS.format(
        n=len(labeled_sops),
        labeled_sops_json=json.dumps(labeled_sops, indent=2),
    ), max_tokens=3000)
    return CrossProcessResult.model_validate(data)


def run_analysis(sops: list[SopInput]) -> RunResult:
    """Full pipeline: 4 tasks per SOP, then optional cross-process."""
    sop_results: list[SingleSopResult] = []

    for sop in sops:
        redesign = run_task1_redesign(sop.text)
        automation = run_task2_automation(sop.text, redesign)
        flowchart = run_task3_flowchart(redesign)
        summary = run_task4_summary(redesign, automation)
        sop_results.append(SingleSopResult(
            sop_input=sop,
            redesign=redesign,
            automation_map=automation,
            flowchart=flowchart,
            executive_summary=summary,
        ))

    cross = None
    if len(sops) > 1:
        labeled = [
            {"label": f"SOP {i+1}: {r.sop_input.process_name or r.redesign.process_name}",
             "text": r.sop_input.text}
            for i, r in enumerate(sop_results)
        ]
        cross = run_cross_process(labeled)

    top_summary = cross.insights if cross else sop_results[-1].executive_summary

    return RunResult(
        sop_results=sop_results,
        cross_process=cross,
        executive_summary=top_summary,
    )
