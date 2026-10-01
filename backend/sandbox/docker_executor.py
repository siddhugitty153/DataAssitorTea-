"""
Docker Sandbox Executor — production-grade secure code execution.

Runs LLM-generated Python code inside an **ephemeral** Docker container.

Security guarantees:
  • Network disabled (no outbound calls)
  • Memory capped (default 512 MB)
  • CPU limited to 1 core
  • Execution timeout (default 30 s)
  • Dataset mounted read-only
  • Container auto-removed after execution

Requires Docker to be available (Docker Desktop or Codespace).
For local dev without Docker, use ``SubprocessSandbox`` instead.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

import docker
from docker.errors import ContainerError, ImageNotFound

from backend.core.sandbox import ExecutionResult, SandboxProvider

logger = logging.getLogger(__name__)


class DockerSandbox(SandboxProvider):
    """Execute Python code in an ephemeral Docker container."""

    def __init__(self) -> None:
        from backend.config import settings
        self.image = settings.sandbox_image
        self.timeout = settings.sandbox_timeout
        self.mem_limit = settings.sandbox_mem_limit

    @property
    def provider_name(self) -> str:
        return "docker"

    async def execute(
        self,
        code: str,
        dataset_path: str,
    ) -> ExecutionResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run, code, dataset_path)

    def _run(self, code: str, dataset_path: str) -> ExecutionResult:
        client = docker.from_env()
        code_file: str | None = None
        container = None
        start_time = time.monotonic()

        try:
            # Verify sandbox image exists
            try:
                client.images.get(self.image)
            except ImageNotFound:
                return ExecutionResult(
                    stderr=(
                        f"Sandbox image '{self.image}' not found. "
                        "Run: docker build -t data-sandbox ./sandbox"
                    ),
                    exit_code=-1,
                    execution_time=time.monotonic() - start_time,
                )

            # Write code to a temp file
            fd, code_file = tempfile.mkstemp(suffix=".py")
            with os.fdopen(fd, "w") as f:
                f.write(code)

            dataset_abs = str(Path(dataset_path).resolve())

            container = client.containers.run(
                image=self.image,
                command=["/sandbox/script.py"],
                volumes={
                    dataset_abs: {
                        "bind": "/sandbox/data/dataset.csv",
                        "mode": "ro",
                    },
                    code_file: {
                        "bind": "/sandbox/script.py",
                        "mode": "ro",
                    },
                },
                mem_limit=self.mem_limit,
                nano_cpus=1_000_000_000,   # 1 CPU core
                network_disabled=True,      # No outbound network
                detach=True,
                remove=False,
            )

            # Block until container exits or timeout
            result = container.wait(timeout=self.timeout)

            stdout = container.logs(stdout=True, stderr=False).decode(
                "utf-8", errors="replace"
            )
            stderr = container.logs(stdout=False, stderr=True).decode(
                "utf-8", errors="replace"
            )

            exit_code = result.get("StatusCode", -1)
            if exit_code != 0 and not stderr:
                stderr = f"Process exited with code {exit_code}.\n{stdout}"

            elapsed = time.monotonic() - start_time

            return ExecutionResult(
                stdout=stdout.strip(),
                stderr=stderr.strip(),
                exit_code=exit_code,
                artifacts={},  # TODO: copy artifacts from container
                execution_time=elapsed,
            )

        except ContainerError as exc:
            logger.exception("Container error")
            return ExecutionResult(
                stderr=f"Container error: {exc}",
                exit_code=-1,
                execution_time=time.monotonic() - start_time,
            )
        except Exception as exc:
            logger.exception("Docker sandbox error")
            return ExecutionResult(
                stderr=f"Execution error: {exc}",
                exit_code=-1,
                execution_time=time.monotonic() - start_time,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            if code_file is not None:
                try:
                    os.unlink(code_file)
                except OSError:
                    pass
