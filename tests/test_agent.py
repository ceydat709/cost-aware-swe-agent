import subprocess

from swe_agent.agent import AgentConfig, parse_command, run_agent, truncate
from swe_agent.cache import ResponseCache, cache_key
from swe_agent.costs import CostTracker
from swe_agent.executor import LocalExecutor


class ScriptedModel:
    def __init__(self, replies):
        self.replies = iter(replies)

    def chat(self, messages):
        return next(self.replies)


def make_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_parse_command():
    assert parse_command("fix it\n```bash\nls -la\n```") == "ls -la"
    assert parse_command("no block here") is None
    assert parse_command("```bash\na\n```\n```bash\nb\n```") is None


def test_truncate_keeps_head_and_tail():
    out = truncate("a" * 50 + "b" * 50, limit=20)
    assert out.startswith("a" * 10) and out.endswith("b" * 10)


def test_agent_fixes_bug_and_submits(tmp_path):
    repo = make_repo(tmp_path)
    model = ScriptedModel([
        "```bash\ncat calc.py\n```",
        "```bash\nsed -i.bak 's/a - b/a + b/' calc.py && rm calc.py.bak\n```",
        "```bash\necho SUBMIT\n```",
    ])
    result = run_agent("add() is wrong", repo, model, LocalExecutor(repo), AgentConfig())
    assert result.exit_reason == "submitted"
    assert "+    return a + b" in result.patch


def test_agent_rejects_empty_submit(tmp_path):
    repo = make_repo(tmp_path)
    model = ScriptedModel([
        "```bash\necho SUBMIT\n```",
        "```bash\nsed -i.bak 's/a - b/a + b/' calc.py && rm calc.py.bak\n```",
        "```bash\necho SUBMIT\n```",
    ])
    result = run_agent("add() is wrong", repo, model, LocalExecutor(repo), AgentConfig())
    assert result.exit_reason == "submitted"
    assert result.steps == 3
    assert "a + b" in result.patch


def test_agent_stops_after_format_errors(tmp_path):
    repo = make_repo(tmp_path)
    model = ScriptedModel(["hmm", "still thinking", "no command"])
    result = run_agent("task", repo, model, LocalExecutor(repo), AgentConfig(max_format_errors=3))
    assert result.exit_reason == "format_errors"
    assert result.patch == ""


def test_cache_roundtrip(tmp_path):
    cache = ResponseCache(tmp_path / "c.sqlite")
    key = cache_key("m", [{"role": "user", "content": "hi"}], {"temperature": 0})
    assert cache.get(key) is None
    cache.put(key, {"content": "hello", "input_tokens": 1, "output_tokens": 1})
    assert cache.get(key)["content"] == "hello"


def test_cost_tracker_skips_cached_calls():
    t = CostTracker()
    t.record("free-model", 100, 50, cached=False)
    t.record("free-model", 100, 50, cached=True)
    assert t.calls == 2 and t.cache_hits == 1 and t.input_tokens == 100
