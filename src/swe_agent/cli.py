"""Run the agent on SWE-bench Lite instances and write predictions for the official harness.

Example:
    swe-agent --model qwen2.5-coder:7b --limit 5 --run-name local-7b
"""

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

from .agent import AgentConfig, run_agent
from .cache import ResponseCache
from .costs import CostTracker
from .executor import SWEBENCH_SETUP, DockerExecutor, LocalExecutor, swebench_image
from .llm import LLM, LLMConfig

DATASET = "SWE-bench/SWE-bench_Lite"


def checkout(repo: str, commit: str, workspace: Path) -> Path:
    """Clone once per repo into a mirror, then make a fresh local clone per task.

    A local clone has its own self-contained .git (objects are hardlinked, so it's cheap),
    which means git also works inside the container. A worktree's .git points at a host
    path that doesn't exist in the container.
    """
    mirror = workspace / "mirrors" / repo.replace("/", "__")
    if not mirror.exists():
        subprocess.run(["git", "clone", "--quiet", f"https://github.com/{repo}.git", str(mirror)], check=True)
    dest = workspace / "tasks" / f"{repo.replace('/', '__')}__{commit[:8]}"
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(["git", "clone", "--quiet", "--local", "--no-checkout", str(mirror), str(dest)], check=True)
    subprocess.run(["git", "checkout", "--quiet", "--detach", commit], cwd=dest, check=True)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--api-key-env", default="LLM_API_KEY")
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--instances", nargs="*", help="instance_ids to run (default: first --limit)")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--verify", action="store_true", help="reject submits that break previously passing tests")
    ap.add_argument("--plain-image", action="store_true",
                    help="use a bare python image instead of the task's SWE-bench image (agent can't run tests)")
    ap.add_argument("--local", action="store_true", help="run commands on the host (unsafe; debugging only)")
    ap.add_argument("--workspace", default="work")
    args = ap.parse_args()

    from datasets import load_dataset

    data = load_dataset(DATASET, split="test")
    if args.instances:
        data = [row for row in data if row["instance_id"] in set(args.instances)]
    else:
        data = list(data)[: args.limit]

    workspace = Path(args.workspace).resolve()  # git worktree runs from the mirror dir, so paths must be absolute
    run_dir = Path("runs") / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    cache = ResponseCache("cache/llm.sqlite")
    preds_path = run_dir / "predictions.jsonl"

    for row in data:
        tracker = CostTracker()
        llm = LLM(LLMConfig(model=args.model, base_url=args.base_url, api_key_env=args.api_key_env), cache, tracker)
        repo = checkout(row["repo"], row["base_commit"], workspace)
        start = time.time()
        if args.local:
            executor = LocalExecutor(repo)
        elif args.plain_image:
            executor = DockerExecutor(repo)
        else:
            executor = DockerExecutor(repo, image=swebench_image(row["instance_id"]), mount="/testbed",
                                      platform="linux/amd64", setup=SWEBENCH_SETUP)
        config = AgentConfig(max_steps=args.max_steps, verify=args.verify)
        try:
            result = run_agent(row["problem_statement"], repo, llm, executor, config)
        finally:
            executor.close()

        with preds_path.open("a") as f:
            f.write(json.dumps({"instance_id": row["instance_id"], "model_name_or_path": args.run_name,
                                "model_patch": result.patch}) + "\n")
        log = {"instance_id": row["instance_id"], "verify": args.verify, "exit_reason": result.exit_reason,
               "steps": result.steps, "verify_rejections": result.verify_rejections,
               "seconds": round(time.time() - start, 1), "cost": tracker.summary()}
        (run_dir / f"{row['instance_id']}.traj.json").write_text(json.dumps({**log, "trajectory": result.trajectory}, indent=2))
        with (run_dir / "costs.jsonl").open("a") as f:
            f.write(json.dumps(log) + "\n")
        print(json.dumps(log))

    print(f"\nPredictions: {preds_path}\nEvaluate with: scripts/evaluate.sh {args.run_name}")


if __name__ == "__main__":
    main()
