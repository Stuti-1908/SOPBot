"""Claude API calls for all 4 WorkflowIQ tasks."""
from __future__ import annotations
import json
import os
from concurrent.futures import ThreadPoolExecutor
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


def _escape_literal_newlines_in_strings(text: str) -> str:
    """Repairs the specific, observed failure mode where Claude returns a
    JSON string value (e.g. TASK3_FLOWCHART's "dot_source") containing real,
    unescaped newline characters instead of the two-character \\n escape -
    valid-looking multi-line text to a human, invalid JSON to a parser.
    Walks the raw text character by character, tracking whether we're
    inside a JSON string (respecting existing backslash-escapes and nested
    escaped quotes), and replaces any literal '\\n' found there with the
    escape sequence. Text outside string values (structural whitespace) is
    left untouched."""
    out = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == '"':
                out.append(ch)
                in_string = False
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            else:
                out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)
    return "".join(out)


def _call(prompt: str, max_tokens: int = MAX_TOKENS) -> dict:
    """Single Claude call; returns parsed JSON dict.

    Claude is instructed to return pure JSON but occasionally prefixes it with
    prose commentary (confirmed to happen on this same model/prompt style in
    SOPBot's transcript extraction). Fall back to locating the JSON object by
    brace-matching rather than trusting json.loads on the raw text alone.

    Also occasionally returns a string VALUE (e.g. dot_source) containing
    real unescaped newlines instead of \\n - confirmed via a real production
    failure on TASK3_FLOWCHART's Graphviz output. A third fallback repairs
    that specific case before giving up.
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
            # The literal-newline repair must run BEFORE brace-matching, not
            # after: an unescaped newline inside a string is exactly what
            # makes brace-matching itself fail ("no balanced closing '}'"),
            # since the parser's notion of being inside/outside a string
            # gets confused by the raw newline. Repairing first fixes the
            # string content so brace-matching (and json.loads) can succeed.
            try:
                repaired_raw = _escape_literal_newlines_in_strings(raw)
                return json.loads(_extract_json_object(repaired_raw))
            except (ValueError, json.JSONDecodeError) as third_err:
                raise ValueError(
                    f"Claude returned invalid JSON: {first_err} | extraction attempt: {second_err} | "
                    f"repair attempt: {third_err} | raw[:500]={raw[:500]!r}"
                ) from third_err


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


def _run_single_sop(sop: SopInput) -> SingleSopResult:
    """One SOP's 4-task pipeline. Task1 must finish first (task2/3/4 all
    depend on its output), but task2 (automation) and task3 (flowchart)
    only depend on task1, not on each other, so they run concurrently -
    task4 (summary) needs task2's result too, so it waits for both."""
    redesign = run_task1_redesign(sop.text)

    with ThreadPoolExecutor(max_workers=2) as inner:
        automation_future = inner.submit(run_task2_automation, sop.text, redesign)
        flowchart_future = inner.submit(run_task3_flowchart, redesign)
        automation = automation_future.result()
        flowchart = flowchart_future.result()

    summary = run_task4_summary(redesign, automation)

    return SingleSopResult(
        sop_input=sop,
        redesign=redesign,
        automation_map=automation,
        flowchart=flowchart,
        executive_summary=summary,
    )


def run_analysis(sops: list[SopInput]) -> RunResult:
    """Full pipeline: 4 tasks per SOP (run_task2/3 in parallel within each
    SOP), then optional cross-process. Every SOP in the batch is fully
    independent of every other, so they're also run concurrently rather
    than one after another - previously a 16-30-SOP report ran up to 30
    sequential 4-call pipelines, which is what made large reports slow."""
    with ThreadPoolExecutor(max_workers=min(len(sops), 8)) as outer:
        sop_results = list(outer.map(_run_single_sop, sops))

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
