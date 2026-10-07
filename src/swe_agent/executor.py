"""Where the agent's shell commands run.

DockerExecutor (default) runs model-written commands inside a container with
only the task repo mounted and no network, so a bad command can't touch your
machine. With a SWE-bench image the repo's dependencies are already installed,
so the agent can run the project's tests. LocalExecutor is for tests and debugging only.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    returncode: int
    output: str


def swebench_image(instance_id: str) -> str:
    """Prebuilt SWE-bench evaluation image for a task (x86_64 only; emulated on Apple Silicon)."""
    return f"swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_')}:latest"


# SWE-bench images keep the repo at /testbed with a ready conda env named "testbed".
SWEBENCH_SETUP = "source /opt/miniconda3/bin/activate testbed && "


class LocalExecutor:
    def __init__(self, workdir: Path, timeout: int = 60):
        self.workdir = workdir
        self.timeout = timeout

    def run(self, command: str, timeout: int | None = None) -> CommandResult:
        timeout = timeout or self.timeout
        try:
            p = subprocess.run(
                ["bash", "-c", command], cwd=self.workdir, capture_output=True, text=True, timeout=timeout
            )
            return CommandResult(p.returncode, p.stdout + p.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(124, f"Command timed out after {timeout}s")

    def close(self) -> None:
        pass


class DockerExecutor:
    def __init__(self, workdir: Path, image: str = "python:3.11-slim", mount: str = "/repo",
                 platform: str | None = None, setup: str = "", timeout: int = 120):
        self.timeout = timeout
        self.setup = setup
        if platform and not _image_exists(image):
            # docker-py and `docker run` don't reliably pick an emulated platform, so pull explicitly.
            subprocess.run(["docker", "pull", "-q", "--platform", platform, image], check=True, capture_output=True)
        cmd = ["docker", "run", "-d", "--rm", "--network", "none", "-v", f"{workdir.resolve()}:{mount}", "-w", mount]
        if platform:
            cmd += ["--platform", platform]
        self.container = subprocess.run(
            cmd + [image, "sleep", "infinity"], capture_output=True, text=True, check=True
        ).stdout.strip()
        # The mounted repo is owned by the host user, not root; without this git refuses to run.
        self.run("git config --global --add safe.directory '*' 2>/dev/null || true")

    def run(self, command: str, timeout: int | None = None) -> CommandResult:
        timeout = timeout or self.timeout
        try:
            p = subprocess.run(
                ["docker", "exec", self.container, "bash", "-c", self.setup + command],
                capture_output=True, text=True, timeout=timeout,
            )
            return CommandResult(p.returncode, p.stdout + p.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(124, f"Command timed out after {timeout}s")

    def close(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.container], capture_output=True)


def _image_exists(image: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0
