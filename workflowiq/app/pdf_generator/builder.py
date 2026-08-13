"""PDF report builder using ReportLab + Graphviz."""
from __future__ import annotations
import os
import io
import re
import tempfile
from datetime import datetime

import graphviz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image, PageBreak,
)

from app.schemas import RunResult, SingleSopResult, AutomationOpportunity

# ── Brand colours ─────────────────────────────────────────────────────────────
BRAND_DARK = colors.HexColor("#1A1A2E")
BRAND_ACCENT = colors.HexColor("#E94560")
BRAND_LIGHT = colors.HexColor("#F5F5F5")


def _normalize_dashes(text: str) -> str:
    """Replace em (—) and en (–) dashes with a plain hyphen. Client requirement:
    no long dashes anywhere in generated reports, only "-"."""
    return text.replace("—", "-").replace("–", "-")


def _inline_markdown_to_reportlab(text: str) -> str:
    """Convert **bold** / *italic* markdown spans to ReportLab's mini-HTML tags."""
    text = _normalize_dashes(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    return text


def _markdown_flowables(md_text: str, styles, body_style) -> list:
    """Render a markdown string (headers, bold/italic, bullets, numbered lists,
    paragraphs) as ReportLab flowables instead of dumping raw markdown syntax
    into a Paragraph, which only understands its own mini-HTML tag subset."""
    flowables = []
    h2 = ParagraphStyle("MdH2", parent=styles["Heading2"], textColor=BRAND_ACCENT, fontSize=14, spaceBefore=6, spaceAfter=4)
    h3 = ParagraphStyle("MdH3", parent=styles["Heading3"], fontSize=12, spaceBefore=4, spaceAfter=3)
    bullet_style = ParagraphStyle("MdBullet", parent=body_style, leftIndent=12, bulletIndent=0, spaceAfter=2)

    for block in md_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("### "):
                flowables.append(Paragraph(_inline_markdown_to_reportlab(line[4:]), h3))
            elif line.startswith("## "):
                flowables.append(Paragraph(_inline_markdown_to_reportlab(line[3:]), h2))
            elif line.startswith("# "):
                flowables.append(Paragraph(_inline_markdown_to_reportlab(line[2:]), h2))
            elif re.match(r"^[-*]\s+", line):
                content = re.sub(r"^[-*]\s+", "", line)
                flowables.append(Paragraph(f"•  {_inline_markdown_to_reportlab(content)}", bullet_style))
            elif re.match(r"^\d+\.\s+", line):
                flowables.append(Paragraph(_inline_markdown_to_reportlab(line), bullet_style))
            else:
                flowables.append(Paragraph(_inline_markdown_to_reportlab(line), body_style))
        flowables.append(Spacer(1, 3*mm))
    return flowables


def build_pdf(result: RunResult) -> str:
    """Build PDF report; return absolute path to the output file."""
    output_dir = os.getenv("OUTPUT_DIR", "./output")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    client = result.sop_results[0].sop_input.client_name or "client"
    safe_client = "".join(c if c.isalnum() else "_" for c in client)
    filename = f"{safe_client}_WorkflowIQ_{timestamp}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm,
        title=f"WorkflowIQ Report - {client}",
    )

    styles = getSampleStyleSheet()
    story = _build_story(result, styles)
    doc.build(story)
    return filepath


def _build_story(result: RunResult, styles) -> list:
    story = []
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=BRAND_DARK, fontSize=22)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=BRAND_ACCENT, fontSize=16)
    body = styles["BodyText"]

    # Cover
    client = result.sop_results[0].sop_input.client_name or "Client"
    story.append(Spacer(1, 30*mm))
    story.append(Paragraph("WorkflowIQ", h1))
    story.append(Paragraph(f"Process Optimization Report", styles["Heading2"]))
    story.append(Paragraph(f"Prepared for: {client}", body))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%B %d, %Y')}", body))
    story.append(HRFlowable(color=BRAND_ACCENT, thickness=2, width="100%"))
    story.append(PageBreak())

    # Executive summary
    story.append(Paragraph("Executive Summary", h1))
    story.append(Spacer(1, 4*mm))
    story += _markdown_flowables(result.executive_summary, styles, body)
    story.append(PageBreak())

    # Per-SOP sections
    for i, sr in enumerate(result.sop_results, 1):
        story += _sop_section(sr, i, h2, body, styles)

    # Cross-process
    if result.cross_process:
        story.append(Paragraph("Cross-Process Insights", h1))
        story.append(Spacer(1, 4*mm))
        story += _markdown_flowables(result.cross_process.insights, styles, body)
        if result.cross_process.shared_bottlenecks:
            story.append(Paragraph("Shared Bottlenecks", h2))
            for b in result.cross_process.shared_bottlenecks:
                story.append(Paragraph(f"• {_normalize_dashes(b)}", body))

    return story


def _sop_section(sr: SingleSopResult, idx: int, h2, body, styles) -> list:
    story = []
    name = sr.redesign.process_name or sr.sop_input.process_name or f"Process {idx}"
    story.append(Paragraph(f"Process {idx}: {name}", h2))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(_normalize_dashes(sr.redesign.current_state_summary), body))
    story.append(Spacer(1, 4*mm))

    # Table cells must be Paragraphs, not plain strings — plain strings in a
    # ReportLab Table do not wrap and instead overflow into adjacent columns
    # when the text is longer than the column width (observed in production:
    # automation opportunity titles/tool names overlapping the Score/Hrs
    # columns).
    cell_style = ParagraphStyle("TableCell", parent=styles["BodyText"], fontSize=9, leading=11)
    header_style = ParagraphStyle(
        "TableHeader", parent=styles["BodyText"], fontSize=9, leading=11,
        textColor=colors.white, fontName="Helvetica-Bold",
    )

    def cell(text) -> Paragraph:
        return Paragraph(_normalize_dashes(str(text)), cell_style)

    def header(text) -> Paragraph:
        return Paragraph(_normalize_dashes(str(text)), header_style)

    # Optimised steps table
    story.append(Paragraph("Optimised Process Steps", styles["Heading3"]))
    table_data = [[header("#"), header("Step"), header("Owner"), header("Time (min)")]]
    for step in sr.redesign.optimised_steps:
        table_data.append([
            cell(step.step_number),
            cell(step.title),
            cell(step.owner or "-"),
            cell(step.estimated_time_minutes if step.estimated_time_minutes else "-"),
        ])
    t = Table(table_data, colWidths=[10*mm, 90*mm, 40*mm, 25*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRAND_LIGHT, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t)
    story.append(Spacer(1, 4*mm))

    # Automation opportunities table
    if sr.automation_map.opportunities:
        story.append(Paragraph("Automation Opportunities", styles["Heading3"]))
        opps = sorted(sr.automation_map.opportunities, key=lambda o: o.composite_score, reverse=True)
        opp_data = [[header("ID"), header("Title"), header("Tool"), header("Score"), header("Hrs/Wk")]]
        for o in opps:
            opp_data.append([
                cell(o.opportunity_id),
                cell(o.title),
                cell(o.tool_suggestion or "-"),
                cell(f"{o.composite_score:.1f}"),
                cell(f"{o.hours_saved_per_week:.1f}" if o.hours_saved_per_week else "-"),
            ])
        t2 = Table(opp_data, colWidths=[18*mm, 65*mm, 45*mm, 18*mm, 18*mm])
        t2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_ACCENT),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRAND_LIGHT, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t2)
        story.append(Spacer(1, 4*mm))

    # Flowchart — own page, vertical layout, sized to fill the page so
    # multi-step processes stay readable instead of shrinking into a
    # 160x80mm strip (was fixed-size + rankdir=LR, illegible past ~5 steps).
    story.append(PageBreak())
    try:
        img_bytes = _render_flowchart(sr.flowchart.dot_source)
        img = Image(
            io.BytesIO(img_bytes),
            width=170*mm, height=240*mm,
            kind="bound",  # scale to fit within bounds, preserve aspect ratio
        )
        story.append(Paragraph("Process Flowchart", styles["Heading3"]))
        story.append(Spacer(1, 3*mm))
        story.append(img)
    except Exception:
        story.append(Paragraph("(Flowchart rendering unavailable)", body))

    story.append(PageBreak())
    return story


def _render_flowchart(dot_source: str) -> bytes:
    """Render DOT source to PNG bytes via system Graphviz."""
    if "rankdir=LR" in dot_source:
        dot_source = dot_source.replace("rankdir=LR", "rankdir=TB")
    elif "rankdir" not in dot_source:
        dot_source = dot_source.replace("{", "{ rankdir=TB;", 1)
    src = graphviz.Source(dot_source, format="png")
    with tempfile.TemporaryDirectory() as tmpdir:
        out = src.render(filename="flowchart", directory=tmpdir, cleanup=True)
        with open(out, "rb") as f:
            return f.read()
