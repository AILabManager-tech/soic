"""SOIC v3.0 — Dashboard: Rich terminal display for gate reports."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .persistence import RunStore


def _status_style(status: str) -> str:
    """Return Rich style for a gate status."""
    styles = {
        "PASS": "bold green",
        "FAIL": "bold red",
        "SKIP": "dim yellow",
        "ERROR": "bold magenta",
    }
    return styles.get(status, "")


def _mu_color(mu: float) -> str:
    """Return color for a mu score."""
    if mu >= 8:
        return "green"
    if mu >= 6:
        return "yellow"
    return "red"


def render_report_table(run: dict[str, Any], console: Console | None = None) -> None:
    """Render a single run report as a Rich table."""
    if console is None:
        console = Console()

    table = Table(
        title=f"SOIC v3.0 -- {run.get('domain', '?')}",
        caption=f"Run: {run.get('run_id', '?')[:12]}...  |  {run.get('timestamp', '?')[:19]}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Gate", style="bold", width=8)
    table.add_column("Name", width=18)
    table.add_column("Status", width=8, justify="center")
    table.add_column("Evidence", width=44)
    table.add_column("Time", width=8, justify="right")

    for g in run.get("gates", []):
        status = g.get("status", "?")
        table.add_row(
            g.get("gate_id", "?"),
            g.get("name", "?"),
            Text(status, style=_status_style(status)),
            (g.get("evidence", ""))[:44],
            f"{g.get('duration_ms', 0)}ms",
        )

    mu = run.get("mu", 0.0)
    pass_rate = run.get("pass_rate", 0.0)
    mu_text = Text(f"mu = {mu:.2f}/10", style=f"bold {_mu_color(mu)}")
    rate_text = Text(f"  Pass rate: {pass_rate:.0%}")

    console.print(table)
    console.print(mu_text, rate_text)
    console.print()


def render_convergence(runs: list[dict[str, Any]], console: Console | None = None) -> None:
    """Render an ASCII convergence chart from multiple runs."""
    if console is None:
        console = Console()

    if not runs:
        console.print("[dim]No runs to display.[/dim]")
        return

    mus = [r.get("mu", 0.0) for r in runs]
    max_mu = 10.0
    chart_height = 8
    chart_width = len(mus)

    console.print(Panel.fit("Convergence mu", style="bold cyan"))

    for row in range(chart_height, 0, -1):
        threshold = (row / chart_height) * max_mu
        label = f"{threshold:>5.1f} |"
        bar = ""
        for mu in mus:
            if mu >= threshold:
                bar += " #"
            else:
                bar += " ."
        console.print(f"  {label}{bar}")

    # X-axis
    axis = "      +" + "--" * chart_width
    console.print(f"  {axis}")
    labels = "       " + " ".join(f"{i}" for i in range(1, chart_width + 1))
    console.print(f"  {labels}")
    console.print()

    # Trend line
    trend_parts = [f"[{_mu_color(m)}]{m:.2f}[/{_mu_color(m)}]" for m in mus]
    console.print(f"  Trend: {' -> '.join(trend_parts)}")
    console.print()


def render_comparison(
    before: dict[str, Any], after: dict[str, Any], console: Console | None = None
) -> None:
    """Render a before/after comparison of two runs."""
    if console is None:
        console = Console()

    table = Table(title="Before / After Comparison", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Before", justify="center")
    table.add_column("After", justify="center")
    table.add_column("Delta", justify="center")

    mu_before = before.get("mu", 0.0)
    mu_after = after.get("mu", 0.0)
    delta_mu = mu_after - mu_before
    delta_style = "green" if delta_mu > 0 else ("red" if delta_mu < 0 else "dim")

    table.add_row(
        "Score mu",
        f"{mu_before:.2f}",
        f"{mu_after:.2f}",
        Text(f"{delta_mu:+.2f}", style=delta_style),
    )

    pr_before = before.get("pass_rate", 0.0)
    pr_after = after.get("pass_rate", 0.0)
    delta_pr = pr_after - pr_before
    pr_style = "green" if delta_pr > 0 else ("red" if delta_pr < 0 else "dim")

    table.add_row(
        "Pass Rate",
        f"{pr_before:.0%}",
        f"{pr_after:.0%}",
        Text(f"{delta_pr:+.0%}", style=pr_style),
    )

    # Per-gate comparison
    before_gates = {g["gate_id"]: g for g in before.get("gates", [])}
    after_gates = {g["gate_id"]: g for g in after.get("gates", [])}

    for gate_id in before_gates:
        bg = before_gates[gate_id]
        ag = after_gates.get(gate_id, bg)
        bs = bg.get("status", "?")
        as_ = ag.get("status", "?")
        if bs != as_:
            change_style = "green" if as_ == "PASS" else "red"
            table.add_row(
                f"  {gate_id} ({bg.get('name', '?')})",
                Text(bs, style=_status_style(bs)),
                Text(as_, style=_status_style(as_)),
                Text("->", style=change_style),
            )

    console.print(table)
    console.print()


def show_dashboard(last: int = 5) -> None:
    """Main dashboard entry point: shows latest run + convergence + comparison."""
    console = Console()
    store = RunStore()
    history = store.get_history(limit=last)

    if not history:
        console.print("[bold red]No SOIC runs found.[/bold red]")
        console.print("Run: python -m soic_v3 evaluate --path <path> --domain CODE")
        return

    # Latest run table
    latest = history[-1]
    render_report_table(latest, console=console)

    # Convergence chart
    if len(history) > 1:
        render_convergence(history, console=console)

    # Before/after comparison
    if len(history) >= 2:
        render_comparison(history[-2], history[-1], console=console)
