#!/usr/bin/env python3
"""
Self-Healing Pipeline Agent — Live Demo
Runs two scenarios and renders the agent flow node by node in the terminal.

Usage:
    uv run python demo.py               # lag_spike + restart_storm
    uv run python demo.py --scenario 1  # lag_spike only
    uv run python demo.py --scenario 2  # restart_storm only (HITL)

Requires: uv run uvicorn api.main:app --reload  (in another terminal)
"""
import json
import sys
import time
import argparse
from pathlib import Path

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text
from rich.rule import Rule

BASE_URL = "http://localhost:8000"
POLL_INTERVAL = 0.4  # seconds between status polls

console = Console()

# ---------------------------------------------------------------------------
# Node display config
# ---------------------------------------------------------------------------

NODE_ORDER = [
    "monitor",
    "diagnosis",
    "remediation",
    "human_checkpoint",
    "executor",
    "verification",
    "learning",
]

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
        "name": "Consumer Lag Spike",
        "subtitle": "auto-resolved · strategy=RESTART · risk=0.30 · no approval needed",
        "file": "simulator/scenarios/lag_spike.json",
    },
    {
        "name": "Restart Storm",
        "subtitle": "high risk · strategy=SAVEPOINT_REDEPLOY · risk=0.85 · pauses for approval",
        "file": "simulator/scenarios/restart_storm.json",
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


def submit_approval(thread_id: str, decision: str) -> dict:
    resp = httpx.post(
        f"{BASE_URL}/approval/{thread_id}",
        json={"decision": decision},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_frame_idx = 0


def _spinner() -> str:
    global _frame_idx
    _frame_idx = (_frame_idx + 1) % len(SPINNER_FRAMES)
    return SPINNER_FRAMES[_frame_idx]


def render_nodes(nodes_completed: list[str], current_node: str | None, paused: bool = False) -> Text:
    text = Text()
    completed_set = set(nodes_completed)

    for node in NODE_ORDER:
        label = NODE_LABELS[node]

        if node in completed_set:
            if node == "human_checkpoint":
                # Show human_checkpoint as approved/acted upon
                text.append("  ✓  ", style="bold cyan")
                text.append(f"{label}\n", style="cyan")
            else:
                text.append("  ✓  ", style="bold green")
                text.append(f"{label}\n", style="green")

        elif node == current_node:
            if paused:
                text.append("  ⏸  ", style="bold yellow")
                text.append(f"{label}\n", style="bold yellow")
            else:
                text.append(f"  {_spinner()}  ", style="bold yellow")
                text.append(f"{label}\n", style="yellow")

        else:
            text.append("     ", style="dim")
            text.append(f"{label}\n", style="dim")

    return text


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def run_scenario(index: int, total: int, scenario: dict) -> None:
    console.print()
    console.print(Rule(
        f"[bold]Scenario {index}/{total}  ·  {scenario['name']}[/bold]",
        style="cyan",
    ))
    console.print(f"  [dim]{scenario['subtitle']}[/dim]\n")

    payload = json.loads(Path(scenario["file"]).read_text())
    console.print(f"  [dim]pipeline:[/dim] {payload.get('pipeline_id', '')}")
    console.print()

    # --- Trigger ---
    console.print("  [cyan]▸[/cyan] Triggering incident...\n")
    t_start = time.time()
    thread_id = trigger_incident(payload)

    # --- Live polling loop ---
    nodes_completed: list[str] = []
    current_node: str | None = None
    status = "processing"

    with Live(render_nodes([], None), console=console, refresh_per_second=6) as live:
        while status == "processing":
            time.sleep(POLL_INTERVAL)
            data = get_status(thread_id)
            status = data.get("status", "processing")
            nodes_completed = data.get("nodes_completed") or []
            current_node = data.get("current_node")
            live.update(render_nodes(nodes_completed, current_node, paused=(status == "awaiting_approval")))

        # Final render
        live.update(render_nodes(nodes_completed, None))

    elapsed = time.time() - t_start

    # --- HITL flow ---
    if status == "awaiting_approval":
        data = get_status(thread_id)
        risk = data.get("risk_score")
        risk_str = f"{risk:.2f}" if risk is not None else "?"

        console.print()
        console.print(Panel(
            f"[bold]Risk score {risk_str}[/bold] exceeds threshold [dim](0.70)[/dim]\n"
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

        t_approval = time.time()
        submit_approval(thread_id, decision)
        elapsed += time.time() - t_approval

        # Refresh node list after approval
        data = get_status(thread_id)
        nodes_completed = data.get("nodes_completed") or []
        status = data.get("status", "resolved")

        console.print(render_nodes(nodes_completed, None))

    # --- Final summary ---
    data = get_status(thread_id)
    anomaly  = data.get("anomaly_type") or "—"
    severity = data.get("severity") or "—"
    risk     = data.get("risk_score")
    risk_str = f"{risk:.2f}" if risk is not None else "—"

    if status in ("resolved", "rejected"):
        icon  = "✅  RESOLVED" if status == "resolved" else "🚫  REJECTED"
        color = "green" if status == "resolved" else "red"
        console.print(Panel(
            f"anomaly   [bold]{anomaly}[/bold]  ·  severity  [bold]{severity}[/bold]\n"
            f"risk      [bold]{risk_str}[/bold]  ·  nodes     [bold]{len(nodes_completed)}[/bold] completed\n"
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
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Self-Healing Pipeline Agent demo")
    parser.add_argument("--scenario", type=int, choices=[1, 2],
                        help="Run a single scenario (1=lag_spike, 2=restart_storm)")
    args = parser.parse_args()

    # Header
    console.print()
    console.print(Panel(
        "[bold cyan]Self-Healing Pipeline Agent[/bold cyan]  —  Live Demo\n"
        "[dim]Autonomous detection · LLM diagnosis · real-time remediation[/dim]",
        border_style="cyan",
        padding=(0, 4),
    ))

    # Health check
    try:
        httpx.get(f"{BASE_URL}/health", timeout=3).raise_for_status()
    except Exception:
        console.print()
        console.print("[bold red]  ✗  API not reachable at http://localhost:8000[/bold red]")
        console.print("  [dim]Start with: uv run uvicorn api.main:app --reload[/dim]")
        sys.exit(1)

    scenarios = [SCENARIOS[args.scenario - 1]] if args.scenario else SCENARIOS
    total = len(scenarios)

    for i, scenario in enumerate(scenarios, 1):
        run_scenario(i, total, scenario)
        if i < total:
            console.print()
            try:
                input("  Press Enter for next scenario... ")
            except (KeyboardInterrupt, EOFError):
                break
            console.print()

    console.print()
    console.print(Panel(
        "[bold cyan]Demo complete.[/bold cyan]\n"
        "[dim]Full traces available in LangSmith (set LANGCHAIN_TRACING_V2=true)[/dim]",
        border_style="cyan",
        padding=(0, 4),
    ))
    console.print()


if __name__ == "__main__":
    main()
