#!/usr/bin/env python3
"""
Self-Healing Pipeline Agent — Live Demo

Flow per scenario:
  1. Trigger incident (POST /incidents)
  2. Spinner while agent runs — audience knows something is happening
  3. Agent finishes → replay decisions node by node with 1s pause
  4. For HITL: pause, show approval panel, prompt, resume, replay remaining nodes
  5. Final summary panel

Scenario 3 (real Flink):
  - Requires Docker Flink cluster running (cd docker && docker compose up)
  - Requires FLINK_REST_URL=http://localhost:8081 in .env
  - Auto-detects running Flink job ID
  - Shows "Watch Flink UI" panel before triggering
  - Verification node shows real polling result (RUNNING ✓) not skipped

Usage:
    uv run python demo.py               # scenarios 1 + 2 (simulated)
    uv run python demo.py --scenario 1  # lag_spike — auto-resolved
    uv run python demo.py --scenario 2  # restart_storm — HITL approval
    uv run python demo.py --scenario 3  # real Flink job restart + verification

Requires: uv run uvicorn api.main:app --reload  (separate terminal)
"""
import json
import os
import sys
import time
import argparse
from pathlib import Path

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.text import Text

BASE_URL = "http://localhost:8000"
POLL_INTERVAL = 0.2   # seconds between status polls while agent runs
REPLAY_PAUSE  = 1.0   # seconds between each node line during replay

console = Console()

NODE_LABELS = {
    "monitor":          "Monitor            rule-based anomaly classification",
    "diagnosis":        "Diagnosis          LLM root cause analysis",
    "remediation":      "Remediation        LLM fix strategy selection",
    "human_checkpoint": "Human Checkpoint   ⏸  awaiting your decision",
    "executor":         "Executor           executing fix strategy",
    "verification":     "Verification       polling Flink for job status",
    "learning":         "Learning           storing outcome to SQLite",
}

SCENARIOS = [
    {
        "name":     "Consumer Lag Spike",
        "subtitle": "auto-resolved · strategy=RESTART · risk=0.30 · no approval needed",
        "file":     "simulator/scenarios/lag_spike.json",
    },
    {
        "name":     "Restart Storm",
        "subtitle": "high risk · strategy=SAVEPOINT_REDEPLOY · risk=0.85 · pauses for approval",
        "file":     "simulator/scenarios/restart_storm.json",
    },
]

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def trigger_incident(payload: dict) -> str:
    resp = httpx.post(f"{BASE_URL}/incidents", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()["thread_id"]


def get_status(thread_id: str) -> dict:
    resp = httpx.get(f"{BASE_URL}/incidents/{thread_id}/status", timeout=10)
    resp.raise_for_status()
    return resp.json()


def submit_approval(thread_id: str, decision: str) -> None:
    resp = httpx.post(
        f"{BASE_URL}/approval/{thread_id}",
        json={"decision": decision},
        timeout=120,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_frame = 0


def _spin() -> str:
    global _frame
    _frame = (_frame + 1) % len(SPINNER_FRAMES)
    return SPINNER_FRAMES[_frame]


def _print_curl_panel(payload: dict, pause: bool = True) -> None:
    """
    Show the curl command that will be sent to POST /incidents.
    If pause=True, wait for Enter before returning so audience can read it.
    """
    body = json.dumps(payload, indent=2)
    # Indent body lines for display inside the panel
    body_lines = "\n".join(f"    {line}" for line in body.splitlines())
    curl_cmd = (
        f"[bold cyan]curl[/bold cyan] -s -X POST {BASE_URL}/incidents \\\n"
        f"  -H [green]'Content-Type: application/json'[/green] \\\n"
        f"  -d [yellow]'{body_lines}'[/yellow]"
    )
    console.print(Panel(
        curl_cmd,
        title="[bold]curl  POST /incidents[/bold]",
        border_style="dim",
        padding=(0, 2),
    ))
    console.print()
    if pause:
        try:
            input("  Press Enter to send... ")
        except (KeyboardInterrupt, EOFError):
            raise SystemExit(0)
        console.print()


def _print_node(node: str, detail, *, cyan: bool = False) -> None:
    """
    Print a completed node with structured received / output sections.
    `detail` is either:
      - a dict: {"received": [...], "label": str, "output": [...]}
      - a str or None: legacy fallback
    """
    label = NODE_LABELS.get(node, node)
    color = "cyan" if cyan else "green"

    header = Text()
    header.append(f"  ✓  ", style=f"bold {color}")
    header.append(label, style=f"bold {color}")
    console.print(header)

    if not detail:
        console.print()
        return

    # Legacy string fallback
    if isinstance(detail, str):
        console.print(Text(f"       → {detail}", style="yellow"))
        console.print()
        return

    # Structured dict: received + output
    indent = "           "

    received = [r for r in (detail.get("received") or []) if r]
    if received:
        console.print(Text(f"       received:", style="bold blue"))
        for line in received:
            console.print(Text(f"{indent}{line}", style="blue"))

    out_label = detail.get("label") or "output"
    output    = [o for o in (detail.get("output") or []) if o]
    if output:
        console.print(Text(f"       {out_label}:", style=f"bold {color}"))
        for line in output:
            console.print(Text(f"{indent}{line}", style=f"bold {color}"))

    console.print()  # blank line between nodes


def _poll_until_done(thread_id: str, t_start: float) -> dict:
    """Show a spinner while the agent runs, return final status data."""
    status = "processing"
    data: dict = {}
    with Live(console=console, refresh_per_second=10) as live:
        while status == "processing":
            elapsed = time.time() - t_start
            live.update(Text(
                f"  {_spin()}  Agent running...  {elapsed:.1f}s",
                style="dim",
            ))
            time.sleep(POLL_INTERVAL)
            data = get_status(thread_id)
            status = data.get("status", "processing")
    return data


def _replay_nodes(nodes: list[str], details: dict) -> None:
    """Print nodes one by one with a pause between each — the core demo effect."""
    console.print()
    console.print("  [dim]▸ Replaying agent decisions...[/dim]\n")
    for node in nodes:
        detail = details.get(node, "")
        _print_node(node, detail, cyan=(node == "human_checkpoint"))
        time.sleep(REPLAY_PAUSE)


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def run_scenario(index: int, total: int, scenario: dict) -> None:
    console.print()
    console.print(Rule(
        f"[bold]Scenario {index}/{total}  ·  {scenario['name']}[/bold]",
        style="cyan",
    ))
    console.print(f"  [dim]{scenario['subtitle']}[/dim]")

    payload = json.loads(Path(scenario["file"]).read_text())
    console.print(f"  [dim]pipeline: {payload.get('pipeline_id', '')}[/dim]\n")

    # 1 — Show curl command, pause for audience, then trigger
    _print_curl_panel(payload, pause=True)
    console.print("  [cyan]▸[/cyan] Sending...\n")
    t_start = time.time()
    thread_id = trigger_incident(payload)

    # 2 — Spinner while agent runs
    data = _poll_until_done(thread_id, t_start)
    status        = data.get("status", "failed")
    nodes         = data.get("nodes_completed") or []
    details       = data.get("node_details") or {}
    elapsed       = time.time() - t_start

    # 3 — Replay pre-approval nodes (or all nodes for non-HITL)
    pre_nodes = nodes  # for non-HITL this is everything
    if status == "awaiting_approval":
        # Replay only the nodes that ran before the pause
        pre_nodes = [n for n in nodes if n not in ("executor", "verification", "learning")]

    _replay_nodes(pre_nodes, details)

    # 4 — HITL approval flow
    if status == "awaiting_approval":
        risk = data.get("risk_score")
        risk_str = f"{risk:.2f}" if risk is not None else "?"

        console.print()
        console.print(Panel(
            f"[bold]Risk score {risk_str}[/bold] exceeds threshold [dim](0.70)[/dim]\n"
            f"Strategy requires human sign-off before execution.\n"
            f"[dim]thread: {thread_id}[/dim]",
            title="[bold yellow]⏸  AWAITING APPROVAL[/bold yellow]",
            border_style="yellow",
            padding=(0, 2),
        ))
        console.print()

        approve = Confirm.ask("  [bold]Approve and execute?[/bold]")
        decision = "APPROVE" if approve else "REJECT"
        console.print()
        console.print(f"  [cyan]▸[/cyan] Submitting {decision}...\n")

        # Resume agent — spinner while it finishes
        t_resume = time.time()
        submit_approval(thread_id, decision)
        elapsed += time.time() - t_resume

        # Get updated nodes after approval
        data = get_status(thread_id)
        status        = data.get("status", "resolved")
        nodes_after   = data.get("nodes_completed") or []
        details_after = data.get("node_details") or {}

        # Replay only the nodes that ran after approval
        post_nodes = [n for n in nodes_after if n not in pre_nodes]
        if post_nodes:
            console.print()
            console.print("  [dim]▸ Resuming after approval...[/dim]\n")
            _replay_nodes(post_nodes, details_after)

        nodes   = nodes_after
        details = details_after

    # 5 — Final summary
    anomaly  = data.get("anomaly_type") or "—"
    severity = data.get("severity") or "—"
    risk     = data.get("risk_score")
    risk_str = f"{risk:.2f}" if risk is not None else "—"

    console.print()
    if status in ("resolved", "rejected"):
        icon  = "✅  RESOLVED" if status == "resolved" else "🚫  REJECTED"
        color = "green" if status == "resolved" else "red"
        console.print(Panel(
            f"anomaly   [bold]{anomaly}[/bold]  ·  severity  [bold]{severity}[/bold]\n"
            f"risk      [bold]{risk_str}[/bold]  ·  nodes     [bold]{len(nodes)}[/bold] completed\n"
            f"[dim]thread: {thread_id}[/dim]",
            title=f"[bold {color}]{icon}[/bold {color}]  [dim]{elapsed:.1f}s[/dim]",
            border_style=color,
            padding=(0, 2),
        ))
    else:
        error = data.get("error", "unknown error")
        console.print(Panel(
            f"[red]{error}[/red]\n[dim]thread: {thread_id}[/dim]",
            title="[bold red]❌  FAILED[/bold red]",
            border_style="red",
            padding=(0, 2),
        ))


# ---------------------------------------------------------------------------
# Scenario 3 — Real Flink job restart
# ---------------------------------------------------------------------------

FLINK_UI = "http://localhost:8081"


def _get_flink_job_id() -> str | None:
    """Auto-detect the first RUNNING job from Flink REST API."""
    try:
        resp = httpx.get(f"{FLINK_UI}/jobs", timeout=5)
        resp.raise_for_status()
        running = [j for j in resp.json().get("jobs", []) if j.get("status") == "RUNNING"]
        return running[0]["id"] if running else None
    except Exception:
        return None


def run_flink_scenario(index: int, total: int) -> None:
    console.print()
    console.print(Rule(
        f"[bold]Scenario {index}/{total}  ·  Kafka Repartition → Incompatible Checkpoint State[/bold]",
        style="cyan",
    ))
    console.print("  [dim]Kafka topic repartitioned 8→12 · checkpoint state incompatible · "
                  "Flink auto-recovery failed twice · agent cancels + resubmits fresh · real Flink polling[/dim]\n")

    # ── Pre-flight checks ────────────────────────────────────────────────────
    flink_url = os.environ.get("FLINK_REST_URL") or os.environ.get("FLINK_REST_URL", "")
    if not flink_url:
        # Try reading from .env manually
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("FLINK_REST_URL="):
                    flink_url = line.split("=", 1)[1].strip()
                    break

    if not flink_url:
        console.print(Panel(
            "[bold red]FLINK_REST_URL is not set.[/bold red]\n"
            "Add to .env:  FLINK_REST_URL=http://localhost:8081\n"
            "Then restart the API server.",
            border_style="red", padding=(0, 2),
        ))
        return

    # Check Flink cluster is reachable
    try:
        httpx.get(f"{FLINK_UI}/jobs", timeout=4).raise_for_status()
    except Exception:
        console.print(Panel(
            f"[bold red]Flink cluster not reachable at {FLINK_UI}[/bold red]\n"
            "Start it with:\n"
            "  cd docker && docker compose up",
            border_style="red", padding=(0, 2),
        ))
        return

    # Auto-detect running job ID
    job_id = _get_flink_job_id()
    if job_id:
        console.print(f"  [dim]auto-detected job:[/dim]  [bold]{job_id}[/bold]")
        console.print()
    else:
        console.print("  [yellow]No RUNNING job detected. Enter job ID manually:[/yellow]")
        job_id = Prompt.ask("  job_id").strip()
        if not job_id:
            console.print("[red]No job ID provided — skipping scenario 3.[/red]")
            return
        console.print()

    # ── Flink UI banner — give audience time to open browser ─────────────────
    console.print(Panel(
        f"[bold cyan]Open the Flink UI now[/bold cyan]\n\n"
        f"  [bold]{FLINK_UI}[/bold]\n\n"
        f"Scenario: Kafka topic [bold]payment-events[/bold] was repartitioned [bold red]8 → 12 partitions[/bold red].\n"
        f"Flink's checkpoint state is incompatible with the new partition topology.\n"
        f"Auto-recovery failed twice — the checkpoint itself is the problem.\n\n"
        f"Agent will cancel the stuck job and resubmit a clean one (no checkpoint restore).\n\n"
        f"Watch the job go:  [bold]RUNNING[/bold]  →  [bold red]CANCELED[/bold red]  →  [bold green]RUNNING[/bold green]\n"
        f"[dim]job_id: {job_id}[/dim]",
        title="[bold cyan]🔗  Flink UI[/bold cyan]",
        border_style="cyan",
        padding=(1, 4),
    ))
    console.print()
    try:
        input("  Press Enter when the Flink UI is open... ")
    except (KeyboardInterrupt, EOFError):
        return
    console.print()

    # ── Build payload with real job ID ───────────────────────────────────────
    payload = {
        "pipeline_id": "payment-pipeline-07",
        "event_type":  "job_failure",
        "metrics": {
            "job_id":              job_id,
            "error_code":          "STATE_INCOMPATIBLE",
            "restart_count":       2,
            "failure_cause":       "Kafka topic repartitioned 8 → 12 partitions — operator state incompatible with new topology",
            "error_message":       "Checkpoint restore failed — KeyGroupRangeOffsetOutOfBoundsException: stored state incompatible with current partition count",
            "topic":               "payment-events",
            "partition_count_old": 8,
            "partition_count_new": 12,
        },
    }

    # ── Show curl command, pause, then trigger ───────────────────────────────
    _print_curl_panel(payload, pause=True)
    console.print(f"  [cyan]▸[/cyan] Sending...\n")

    t_start   = time.time()
    thread_id = trigger_incident(payload)

    console.print("  [dim]▸ Watch the Flink UI — agent canceling incompatible job, resubmitting clean[/dim]\n")

    # ── Spinner while agent runs ──────────────────────────────────────────────
    data    = _poll_until_done(thread_id, t_start)
    status  = data.get("status", "failed")
    nodes   = data.get("nodes_completed") or []
    details = data.get("node_details") or {}
    elapsed = time.time() - t_start

    # ── Replay all nodes ──────────────────────────────────────────────────────
    _replay_nodes(nodes, details)

    # ── Final summary ─────────────────────────────────────────────────────────
    anomaly  = data.get("anomaly_type") or "—"
    severity = data.get("severity")     or "—"
    risk     = data.get("risk_score")
    risk_str = f"{risk:.2f}" if risk is not None else "—"

    console.print()
    if status == "resolved":
        console.print(Panel(
            f"anomaly   [bold]{anomaly}[/bold]  ·  severity  [bold]{severity}[/bold]\n"
            f"risk      [bold]{risk_str}[/bold]  ·  nodes     [bold]{len(nodes)}[/bold] completed\n"
            f"[dim]Flink job is back RUNNING — check {FLINK_UI}[/dim]\n"
            f"[dim]thread: {thread_id}[/dim]",
            title=f"[bold green]✅  RESOLVED[/bold green]  [dim]{elapsed:.1f}s[/dim]",
            border_style="green",
            padding=(0, 2),
        ))
    else:
        error = data.get("error", "unknown error")
        console.print(Panel(
            f"[red]{error}[/red]\n[dim]thread: {thread_id}[/dim]",
            title="[bold red]❌  FAILED[/bold red]",
            border_style="red",
            padding=(0, 2),
        ))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Self-Healing Pipeline Agent — live demo")
    parser.add_argument(
        "--scenario", type=int, choices=[1, 2, 3],
        help="1=lag_spike (auto)  2=restart_storm (HITL)  3=real Flink restart",
    )
    args = parser.parse_args()

    console.print()
    console.print(Panel(
        "[bold cyan]Self-Healing Pipeline Agent[/bold cyan]  —  Live Demo\n"
        "[dim]Autonomous detection  ·  LLM diagnosis  ·  real-time remediation[/dim]",
        border_style="cyan",
        padding=(0, 4),
    ))

    try:
        httpx.get(f"{BASE_URL}/health", timeout=3).raise_for_status()
    except Exception:
        console.print()
        console.print("[bold red]  ✗  API not reachable at http://localhost:8000[/bold red]")
        console.print("  [dim]Run: uv run uvicorn api.main:app --reload[/dim]")
        sys.exit(1)

    # Scenario 3 is handled separately (requires Flink)
    if args.scenario == 3:
        run_flink_scenario(1, 1)
    else:
        scenarios = [SCENARIOS[args.scenario - 1]] if args.scenario else SCENARIOS
        total     = len(scenarios)
        for i, scenario in enumerate(scenarios, 1):
            run_scenario(i, total, scenario)
            if i < total:
                console.print()
                try:
                    input("  Press Enter for next scenario... ")
                except (KeyboardInterrupt, EOFError):
                    break

    console.print()
    console.print(Panel(
        "[bold cyan]Demo complete.[/bold cyan]\n"
        "[dim]Full LLM traces available in LangSmith (LANGCHAIN_TRACING_V2=true)[/dim]",
        border_style="cyan",
        padding=(0, 4),
    ))
    console.print()


if __name__ == "__main__":
    main()
