"""Where the agent's shell commands run.

DockerExecutor (default) runs model-written commands inside a container with
only the task repo mounted, so a bad command can't touch your machine.
LocalExecutor is for tests and debugging only.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    returncode: int
    output: str


class LocalExecutor:
    def __init__(self, workdir: Path, timeout: int = 60):
        self.workdir = workdir
        self.timeout = timeout

    def run(self, command: str) -> CommandResult:
        try:
            p = subprocess.run(
                ["bash", "-c", command], cwd=self.workdir, capture_output=True, text=True, timeout=self.timeout
            )
            return CommandResult(p.returncode, p.stdout + p.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(124, f"Command timed out after {self.timeout}s")

    def close(self) -> None:
        pass


class DockerExecutor:
    def __init__(self, workdir: Path, image: str = "python:3.11-slim", timeout: int = 60):
        self.timeout = timeout
        self.container = subprocess.run(
            ["docker", "run", "-d", "--rm", "--network", "none", "-v", f"{workdir.resolve()}:/repo", "-w", "/repo",
             image, "sleep", "infinity"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    def run(self, command: str) -> CommandResult:
        try:
            p = subprocess.run(
                ["docker", "exec", self.container, "bash", "-c", command],
                capture_output=True, text=True, timeout=self.timeout,
            )
            return CommandResult(p.returncode, p.stdout + p.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(124, f"Command timed out after {self.timeout}s")

    def close(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.container], capture_output=True)
