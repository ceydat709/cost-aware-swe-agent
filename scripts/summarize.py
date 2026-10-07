"""Print a comparison table for one or more runs.

Usage: python scripts/summarize.py <run-name> [<run-name> ...]

Combines the agent's per-task logs (runs/<run>/costs.jsonl) with the official
harness report (runs/<run>/*.<run>.json).
"""

import glob
import json
import sys
from pathlib import Path


def load_run(run: str) -> dict:
    run_dir = Path("runs") / run
    tasks = [json.loads(line) for line in (run_dir / "costs.jsonl").read_text().splitlines() if line.strip()]
    reports = glob.glob(str(run_dir / f"*.{run}.json"))
    resolved = set(json.loads(Path(reports[0]).read_text())["resolved_ids"]) if reports else None
    return {"tasks": tasks, "resolved": resolved}


def summarize(run: str) -> dict:
    data = load_run(run)
    tasks, resolved = data["tasks"], data["resolved"]
    n = len(tasks)
    exits = {}
    for t in tasks:
        exits[t["exit_reason"]] = exits.get(t["exit_reason"], 0) + 1
    return {
        "run": run,
        "tasks": n,
        "resolved": "not scored" if resolved is None else f"{len(resolved)}/{n}",
        "avg_steps": round(sum(t["steps"] for t in tasks) / n, 1) if n else 0,
        "avg_min": round(sum(t["seconds"] for t in tasks) / n / 60, 1) if n else 0,
        "rejections": sum(t.get("verify_rejections", 0) for t in tasks),
        "cost_usd": round(sum(t["cost"]["dollars"] for t in tasks), 4),
        "exits": ", ".join(f"{k}={v}" for k, v in sorted(exits.items())),
    }


def main() -> None:
    rows = [summarize(run) for run in sys.argv[1:]]
    cols = ["run", "tasks", "resolved", "avg_steps", "avg_min", "rejections", "cost_usd", "exits"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")


if __name__ == "__main__":
    main()
