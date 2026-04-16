"""Generate a markdown summary report for a completed eval run."""

from __future__ import annotations

from pathlib import Path

REPORTS_PATH = Path(__file__).resolve().parent.parent.parent / "outputs" / "reports"


def _status(score: float, threshold: float, lower_is_better: bool = False) -> str:
    if lower_is_better:
        return "PASS" if score <= threshold else "FAIL"
    return "PASS" if score >= threshold else "FAIL"


def generate_markdown(
    run_id: str,
    model: str,
    rag_aggregates: dict[str, float],
    rag_thresholds: dict[str, float],
    agent_aggregates: dict[str, float],
    agent_thresholds: dict[str, float],
    overall: str,
    cost_usd: float,
    total_tokens: int,
) -> str:
    lines = [
        f"# Eval Run: {run_id}",
        "",
        f"**Model:** {model}  ",
        f"**Overall:** `{overall}`  ",
        f"**Cost:** ${cost_usd:.4f}  ",
        f"**Tokens:** {total_tokens:,}",
        "",
        "---",
        "",
        "## RAG Metrics",
        "",
        "| Metric | Score | Threshold | Status |",
        "|---|---|---|---|",
    ]

    lower_is_better_rag = set()
    for metric, score in rag_aggregates.items():
        threshold = rag_thresholds.get(metric, 0.0)
        lower = metric in lower_is_better_rag
        status = _status(score, threshold, lower_is_better=lower)
        icon = "✅" if status == "PASS" else "❌"
        lines.append(f"| {metric} | {score:.4f} | {threshold} | {icon} {status} |")

    lines += [
        "",
        "## Agent Metrics",
        "",
        "| Metric | Score | Threshold | Status |",
        "|---|---|---|---|",
    ]

    lower_is_better_agent = {"false_positive_rate"}
    for metric, score in agent_aggregates.items():
        threshold = agent_thresholds.get(metric, 0.0)
        lower = metric in lower_is_better_agent
        status = _status(score, threshold, lower_is_better=lower)
        icon = "✅" if status == "PASS" else "❌"
        lines.append(f"| {metric} | {score:.4f} | {threshold} | {icon} {status} |")

    lines += ["", "---", ""]
    return "\n".join(lines)


def save_report(content: str, run_id: str) -> Path:
    """Save the markdown report and overwrite latest_report.md."""
    REPORTS_PATH.mkdir(parents=True, exist_ok=True)

    run_path = REPORTS_PATH / f"{run_id}.md"
    latest_path = REPORTS_PATH / "latest_report.md"

    run_path.write_text(content)
    latest_path.write_text(content)

    return latest_path
