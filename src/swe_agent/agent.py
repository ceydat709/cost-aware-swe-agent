"""The agent loop.

The model replies with exactly one ```bash block per turn; we run it and send
back the output. This text protocol works with small local models that don't
support function calling. The agent finishes by running `echo SUBMIT`.
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .executor import CommandResult

SYSTEM_PROMPT = """You are a software engineer fixing a bug in the repository at the current directory.
Each turn, think briefly, then reply with EXACTLY ONE shell command in a ```bash block.
Use commands like grep, sed -n, cat, python, and sed -i or a python script to edit files.
Do not modify tests. When the fix is complete, reply with:
```bash
echo SUBMIT
```"""

BASH_BLOCK = re.compile(r"```(?:bash|sh)?\s*\n(.*?)```", re.DOTALL)
MAX_OUTPUT_CHARS = 4000


class ChatModel(Protocol):
    def chat(self, messages: list[dict]) -> str: ...


class Executor(Protocol):
    def run(self, command: str) -> CommandResult: ...


@dataclass
class AgentConfig:
    max_steps: int = 30
    max_format_errors: int = 3


@dataclass
class AgentResult:
    patch: str
    exit_reason: str  # submitted | max_steps | format_errors
    steps: int
    trajectory: list[dict] = field(default_factory=list)


def parse_command(reply: str) -> str | None:
    blocks = BASH_BLOCK.findall(reply)
    return blocks[0].strip() if len(blocks) == 1 else None


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n... [{len(text) - limit} chars truncated] ...\n{text[-half:]}"


def git_diff(repo: Path) -> str:
    return subprocess.run(["git", "diff"], cwd=repo, capture_output=True, text=True).stdout


def run_agent(task: str, repo: Path, model: ChatModel, executor: Executor, config: AgentConfig) -> AgentResult:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": task}]
    format_errors = 0
    exit_reason = "max_steps"
    step = 0

    for step in range(1, config.max_steps + 1):
        reply = model.chat(messages)
        messages.append({"role": "assistant", "content": reply})

        command = parse_command(reply)
        if command is None:
            format_errors += 1
            if format_errors >= config.max_format_errors:
                exit_reason = "format_errors"
                break
            messages.append({"role": "user", "content": "Reply with exactly one ```bash block."})
            continue

        if command == "echo SUBMIT":
            exit_reason = "submitted"
            break

        result = executor.run(command)
        observation = f"exit code: {result.returncode}\n{truncate(result.output)}"
        messages.append({"role": "user", "content": observation})

    return AgentResult(patch=git_diff(repo), exit_reason=exit_reason, steps=step, trajectory=messages)
