"""SOIC v3.0 — CLI: command-line interface for gate evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Import domain grids to trigger auto-registration
import soic_v3.domain_grids.code  # noqa: F401
import soic_v3.domain_grids.infra  # noqa: F401
import soic_v3.domain_grids.prompt  # noqa: F401
import soic_v3.domain_grids.prose  # noqa: F401
from .classifier import classify_domain
from .converger import Decision
from .gate_engine import GateEngine
from .iterator import SOICIterator
from .models import GateReport, GateStatus
from .persistence import RunStore


def _format_table(report: GateReport) -> str:
    """Format gate results as an ASCII table."""
    lines: list[str] = []
    lines.append("")
    lines.append(f"  SOIC v3.0 -- Domain: {report.domain}")
    lines.append(f"  Target: {report.target_path}")
    lines.append(f"  Run ID: {report.run_id}")
    lines.append("")
    lines.append(f"  {'Gate':<8} {'Name':<18} {'Status':<8} {'Evidence':<40} {'Time':>8}")
    lines.append(f"  {'---'*3:<8} {'---'*6:<18} {'---'*3:<8} {'---'*13:<40} {'---'*3:>8}")

    for g in report.gates:
        status_str = g.status.value
        evidence = g.evidence[:40]
        time_str = f"{g.duration_ms}ms"
        lines.append(
            f"  {g.gate_id:<8} {g.name:<18} {status_str:<8} {evidence:<40} {time_str:>8}"
        )

    lines.append("")
    lines.append(f"  Score mu: {report.mu:.2f}/10  |  Pass rate: {report.pass_rate:.0%}")
    lines.append("")
    return "\n".join(lines)


def _resolve_domains(args: argparse.Namespace) -> list[str]:
    """Resolve domain(s) from args: explicit or auto-detected."""
    if args.domain:
        return [d.strip().upper() for d in args.domain.split(",")]
    detected = classify_domain(args.path)
    print(f"  Auto-detected domain(s): {', '.join(detected)}")
    return detected


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Execute the evaluate command."""
    domains = _resolve_domains(args)
    store = RunStore()
    has_any_failure = False

    for domain in domains:
        engine = GateEngine(
            domain=domain,
            target_path=args.path,
            test_path=getattr(args, "test_path", None),
        )
        report = engine.run_all_gates()
        store.save_run(report)

        if args.output == "json":
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(_format_table(report))

        if any(g.status in (GateStatus.FAIL, GateStatus.ERROR) for g in report.gates):
            has_any_failure = True

    return 1 if has_any_failure else 0


def cmd_iterate(args: argparse.Namespace) -> int:
    """Execute the iterate command: evaluate-decide-feedback loop."""
    domains = _resolve_domains(args)
    overall_exit = 0

    for domain in domains:
        if len(domains) > 1:
            print(f"\n{'#' * 60}")
            print(f"  Domain: {domain}")
            print(f"{'#' * 60}")

        iterator = SOICIterator(
            domain=domain,
            target_path=args.path,
            test_path=getattr(args, "test_path", None),
            max_iter=args.max_iter,
        )

        def on_iteration(i: int, result, _max=args.max_iter) -> None:  # noqa: ANN001
            """Print each iteration's results in real time."""
            print(f"\n{'=' * 60}")
            print(f"  Iteration {i}/{_max}")
            print(f"{'=' * 60}")
            print(_format_table(result.report))
            print(f"  Decision: {result.summary}")
            if result.decision == Decision.ITERATE:
                print(f"\n{result.feedback}")

        loop_result = iterator.run(on_iteration=on_iteration)

        # Final summary
        print(f"\n{'=' * 60}")
        print("  FINAL RESULT")
        print(f"{'=' * 60}")
        print(f"  Iterations: {loop_result.total_iterations}")
        print(f"  Decision:   {loop_result.final_decision.value}")
        print(f"  Final mu:   {loop_result.final_mu:.2f}/10")

        if loop_result.total_iterations > 1:
            print("\n  Convergence: ", end="")
            mus = [it.report.mu for it in loop_result.iterations]
            print(" -> ".join(f"{m:.2f}" for m in mus))

        print()

        if loop_result.final_decision != Decision.ACCEPT:
            overall_exit = 1

    return overall_exit


def cmd_history(args: argparse.Namespace) -> int:
    """Execute the history command."""
    store = RunStore()

    # Web history by target URL
    target = getattr(args, "target", None)
    if target and target.startswith("http"):
        history = store.get_web_history(target, limit=args.last)
        if not history:
            print("  No web scans found for this URL.")
            return 0
        if args.output == "json":
            print(json.dumps(history, indent=2, ensure_ascii=False))
            return 0
        print(f"\n  {'Score':>8} {'Grade':<12} {'Timestamp':<26}")
        print(f"  {'---'*3:>8} {'---'*4:<12} {'---'*9:<26}")
        for run in history:
            score = run.get("osiris_score", 0.0)
            grade = run.get("grade", "?")
            ts = run.get("timestamp", "?")[:25]
            print(f"  {score:>8.2f} {grade:<12} {ts:<26}")
        print()
        return 0

    # Gate history (code evaluation)
    history = store.get_history(limit=args.last)
    if not history:
        print("  No runs found.")
        return 0

    if args.output == "json":
        print(json.dumps(history, indent=2, ensure_ascii=False))
        return 0

    print(
        f"\n  {'Run ID':<38} {'Domain':<8} {'mu':>6} {'Pass Rate':>10} {'Timestamp':<26}"
    )
    print(f"  {'---'*13:<38} {'---'*3:<8} {'---'*2:>6} {'---'*3:>10} {'---'*9:<26}")
    for run in history:
        run_id = run.get("run_id", "?")[:36]
        domain = run.get("domain", "?")
        mu = run.get("mu", 0.0)
        pass_rate = run.get("pass_rate", 0.0)
        ts = run.get("timestamp", "?")[:25]
        print(f"  {run_id:<38} {domain:<8} {mu:>6.2f} {pass_rate:>9.0%} {ts:<26}")
    print()
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Execute the dashboard command."""
    from .dashboard import show_dashboard

    show_dashboard(last=args.last)
    return 0


def _report_to_sarif(run: dict) -> dict:
    """Convert a SOIC run to SARIF format."""
    results = []
    for g in run.get("gates", []):
        if g.get("status") in ("FAIL", "ERROR"):
            results.append({
                "ruleId": g.get("gate_id", "unknown"),
                "level": "error" if g.get("status") == "FAIL" else "warning",
                "message": {
                    "text": f"{g.get('name', '?')}: {g.get('evidence', 'No details')}",
                },
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": run.get("target_path", "."),
                        },
                    },
                }],
            })

    return {
        "$schema": (
            "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/"
            "main/sarif-2.1/schema/sarif-schema-2.1.0.json"
        ),
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "SOIC",
                    "version": "3.0",
                    "rules": [
                        {
                            "id": g.get("gate_id", "unknown"),
                            "shortDescription": {"text": g.get("name", "?")},
                        }
                        for g in run.get("gates", [])
                        if g.get("status") in ("FAIL", "ERROR")
                    ],
                },
            },
            "results": results,
        }],
    }


def cmd_export(args: argparse.Namespace) -> int:
    """Export the latest run in SARIF format."""
    store = RunStore()
    latest = store.get_latest()

    if not latest:
        print("  No runs found. Run an evaluation first.")
        return 1

    sarif = _report_to_sarif(latest)
    output_str = json.dumps(sarif, indent=2, ensure_ascii=False)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output_str, encoding="utf-8")
        print(f"  SARIF report written to: {output_path}")
    else:
        print(output_str)

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="soic",
        description="SOIC v3.0 -- Tool-verified quality gates",
    )
    subparsers = parser.add_subparsers(dest="command")

    # evaluate
    eval_parser = subparsers.add_parser("evaluate", help="Run all gates for a domain")
    eval_parser.add_argument("--path", required=True, help="Target path to evaluate")
    eval_parser.add_argument(
        "--domain", default=None,
        help="Domain grid (e.g. CODE, PROSE, INFRA, PROMPT) or comma-separated.",
    )
    eval_parser.add_argument("--test-path", default=None, help="Path to tests (for pytest gate)")
    eval_parser.add_argument(
        "--output", choices=["table", "json"], default="table", help="Output format",
    )

    # iterate
    iter_parser = subparsers.add_parser("iterate", help="Run evaluate-decide-feedback loop")
    iter_parser.add_argument("--path", required=True, help="Target path to evaluate")
    iter_parser.add_argument("--domain", default=None, help="Domain grid or comma-separated.")
    iter_parser.add_argument("--test-path", default=None, help="Path to tests (for pytest gate)")
    iter_parser.add_argument(
        "--max-iter", type=int, default=3, help="Max iterations (default: 3)",
    )

    # history
    hist_parser = subparsers.add_parser("history", help="Show run history")
    hist_parser.add_argument(
        "--target", default=None, help="Target URL or path to show history for",
    )
    hist_parser.add_argument(
        "--last", type=int, default=10, help="Number of recent runs to show",
    )
    hist_parser.add_argument(
        "--output", choices=["table", "json"], default="table", help="Output format",
    )

    # dashboard
    dash_parser = subparsers.add_parser("dashboard", help="Show Rich dashboard")
    dash_parser.add_argument(
        "--last", type=int, default=5, help="Number of recent runs to display",
    )

    # export
    export_parser = subparsers.add_parser("export", help="Export report")
    export_parser.add_argument(
        "--format", choices=["sarif"], default="sarif", help="Export format",
    )
    export_parser.add_argument(
        "--output", default=None, help="Output file path (stdout if omitted)",
    )

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "evaluate": cmd_evaluate,
        "iterate": cmd_iterate,
        "history": cmd_history,
        "dashboard": cmd_dashboard,
        "export": cmd_export,
    }

    handler = commands.get(args.command)
    if handler:
        exit_code = handler(args)
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
