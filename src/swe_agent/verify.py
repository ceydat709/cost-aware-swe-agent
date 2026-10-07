"""Verify-before-submit: reject patches that break tests that used to pass.

We only use tests that already exist in the repo (never SWE-bench's hidden
grading tests). Tests are run on the original code and on the patched code;
a test that passed before and fails now is a regression. Comparing against the
original code ignores tests that fail regardless (e.g. ones needing network).
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

RESULT_LINE = re.compile(r"^(PASSED|FAILED|ERROR) (\S+)", re.MULTILINE)


@dataclass
class TestRun:
    passed: set[str]
    failed: set[str]
    output: str


@dataclass
class Verdict:
    ok: bool
    regressions: list[str]
    tests_run: int
    message: str


def changed_files(repo: Path, base: str) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", base], cwd=repo, capture_output=True, text=True).stdout
    return [f for f in out.splitlines() if f.endswith(".py")]


def find_test_files(repo: Path, changed: list[str]) -> list[str]:
    """Test files for changed modules (test_foo.py / foo_test.py); falls back to all top-level-ish tests."""
    all_tests = sorted(
        str(p.relative_to(repo)) for p in repo.rglob("*.py")
        if (p.name.startswith("test_") or p.name.endswith("_test.py")) and ".git" not in p.parts
    )
    stems = {Path(f).stem for f in changed if not Path(f).name.startswith("test_")}
    matched = [t for t in all_tests if Path(t).stem.removeprefix("test_").removesuffix("_test") in stems]
    matched += [f for f in changed if f in all_tests]  # tests the agent edited or added
    if matched:
        return sorted(set(matched))
    return all_tests[:5]  # small repos (e.g. requests) keep everything in one or two files


def parse_pytest(output: str) -> TestRun:
    passed, failed = set(), set()
    for status, test_id in RESULT_LINE.findall(output):
        (passed if status == "PASSED" else failed).add(test_id)
    return TestRun(passed, failed, output)


def run_tests(executor, files: list[str], test_command: str, timeout: int) -> TestRun:
    # Python reuses .pyc files when a source file's size and whole-second mtime match. A same-size
    # edit made within a second of the baseline run would then test the *original* code, so clear
    # the caches and don't write new ones.
    clear = "find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null; "
    cmd = f"{clear}PYTHONDONTWRITEBYTECODE=1 {test_command} -rA -q --tb=no -p no:cacheprovider {' '.join(files)}"
    return parse_pytest(executor.run(cmd, timeout=timeout).output)


def verify(repo: Path, base: str, executor, test_command: str, timeout: int, baseline_cache: dict) -> Verdict:
    files = find_test_files(repo, changed_files(repo, base))
    if not files:
        return Verdict(True, [], 0, "No related tests found; submitting.")

    key = tuple(files)
    if key not in baseline_cache:
        # If the agent committed or moved HEAD, fold that back into uncommitted changes so
        # stashing really restores the original code.
        subprocess.run(["git", "reset", "-q", "--soft", base], cwd=repo, check=True)
        subprocess.run(["git", "stash", "-q"], cwd=repo, check=True)
        try:
            baseline_cache[key] = run_tests(executor, files, test_command, timeout)
        finally:
            subprocess.run(["git", "stash", "pop", "-q"], cwd=repo, check=True)
    before = baseline_cache[key]
    after = run_tests(executor, files, test_command, timeout)

    regressions = sorted(before.passed - after.passed)
    if not regressions:
        return Verdict(True, [], len(after.passed | after.failed),
                       f"Verification passed: no regressions in {', '.join(files)}.")
    shown = "\n".join(regressions[:20])
    more = f"\n... and {len(regressions) - 20} more" if len(regressions) > 20 else ""
    return Verdict(False, regressions, len(after.passed | after.failed),
                   f"Submit rejected: your change broke {len(regressions)} test(s) that passed before:\n"
                   f"{shown}{more}\nFix the regression, then submit again.")
