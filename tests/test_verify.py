import subprocess
import sys

from swe_agent.agent import AgentConfig, run_agent
from swe_agent.executor import LocalExecutor
from swe_agent.verify import find_test_files, parse_pytest

TEST_FILE = """from calc import add, sub

def test_add():
    assert add(2, 2) == 4

def test_sub():
    assert sub(5, 3) == 2

def test_needs_network():
    raise ConnectionError("no network in sandbox")  # fails before and after: not a regression
"""


class ScriptedModel:
    def __init__(self, replies):
        self.replies = iter(replies)

    def chat(self, messages):
        return next(self.replies)


def make_repo(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a + b\n")
    (tmp_path / "test_calc.py").write_text(TEST_FILE)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


def config():
    return AgentConfig(verify=True, test_command=f"{sys.executable} -m pytest", test_timeout=60)


def test_parse_pytest():
    out = "PASSED t.py::a\nFAILED t.py::b - AssertionError\nERROR t.py::c\n"
    run = parse_pytest(out)
    assert run.passed == {"t.py::a"} and run.failed == {"t.py::b", "t.py::c"}


def test_find_test_files_matches_module(tmp_path):
    repo = make_repo(tmp_path)
    assert find_test_files(repo, ["calc.py"]) == ["test_calc.py"]


def test_regression_is_rejected_then_fix_is_accepted(tmp_path):
    repo = make_repo(tmp_path)
    model = ScriptedModel([
        # Breaks add() while "fixing" sub(): test_add regresses.
        "```bash\nsed -i.bak 's/return a + b/return a - b/' calc.py && rm calc.py.bak\n```",
        "```bash\necho SUBMIT\n```",
        # Restore add(), keep the sub() fix.
        "```bash\npython3 -c \"import re,pathlib;p=pathlib.Path('calc.py');"
        "p.write_text('def add(a, b):\\n    return a + b\\n\\ndef sub(a, b):\\n    return a - b\\n')\"\n```",
        "```bash\necho SUBMIT\n```",
    ])
    result = run_agent("sub() is wrong", repo, model, LocalExecutor(repo), config())
    assert result.exit_reason == "submitted"
    assert result.verify_rejections == 1
    rejection = next(m["content"] for m in result.trajectory if "Submit rejected" in m["content"])
    assert "test_calc.py::test_add" in rejection and "test_needs_network" not in rejection


def test_agent_can_undo_with_git_and_commits_are_handled(tmp_path):
    repo = make_repo(tmp_path)
    model = ScriptedModel([
        # Commits a breaking change; verify must still see it (diff is against the start commit).
        "```bash\nsed -i.bak 's/return a + b/return a - b/' calc.py && rm calc.py.bak && "
        "git -c user.name=a -c user.email=a@a commit -qam wip\n```",
        "```bash\necho SUBMIT\n```",
        # Undoes it with git, then makes the right fix.
        "```bash\ngit checkout -- calc.py\n```",
        "```bash\npython3 -c \"import pathlib;p=pathlib.Path('calc.py');"
        "p.write_text(p.read_text().replace('def sub(a, b):\\n    return a + b', 'def sub(a, b):\\n    return a - b'))\"\n```",
        "```bash\necho SUBMIT\n```",
    ])
    result = run_agent("sub() is wrong", repo, model, LocalExecutor(repo), config())
    assert result.verify_rejections == 1
    assert result.exit_reason == "submitted"
    assert "+    return a - b" in result.patch and result.patch.count("+    return") == 1


def test_gives_up_after_max_verify_failures(tmp_path):
    repo = make_repo(tmp_path)
    breaking_edit = "```bash\nsed -i.bak 's/return a + b/return a - b/' calc.py && rm calc.py.bak\n```"
    model = ScriptedModel([breaking_edit] + ["```bash\necho SUBMIT\n```"] * 3)
    result = run_agent("sub() is wrong", repo, model, LocalExecutor(repo), config())
    assert result.exit_reason == "verify_failed"
    assert result.verify_rejections == 3
    assert result.patch  # the patch is still recorded so the harness can score it
