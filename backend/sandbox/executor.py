"""
Docker Sandbox Executor — The Hands

Runs LLM-generated Python code inside an **ephemeral** Docker container.

Security guarantees:
  • Network disabled (no outbound calls)
  • Memory capped (default 512 MB)
  • CPU limited to 1 core
  • Execution timeout (default 30 s)
  • Dataset mounted read-only
  • Container auto-removed after execution
  • Runs as non-root `sandboxuser` inside the image
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

import docker
from docker.errors import ContainerError, ImageNotFound

from backend.config import settings

logger = logging.getLogger(__name__)


class SandboxExecutor:
    """Create, run, and destroy ephemeral Docker containers for code execution."""

    def __init__(self) -> None:
        self.image = settings.sandbox_image
        self.timeout = settings.sandbox_timeout
        self.mem_limit = settings.sandbox_mem_limit

    # ── Public async API ──────────────────────────────────────

    async def execute(self, code: str, dataset_path: str) -> tuple[str, str]:
        """
        Execute *code* with *dataset_path* mounted read-only.

        Returns (stdout, stderr).  Non-empty stderr signals failure.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._run, code, dataset_path
        )

    # ── Private sync implementation ───────────────────────────

    def _run(self, code: str, dataset_path: str) -> tuple[str, str]:
        client = docker.from_env()
        code_file: str | None = None
        container = None

        try:
            # Verify sandbox image exists
            try:
                client.images.get(self.image)
            except ImageNotFound:
                return "", (
                    f"Sandbox image '{self.image}' not found. "
                    "Run: docker build -t data-sandbox ./sandbox"
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

            # Non-zero exit code → treat stdout as part of error info
            exit_code = result.get("StatusCode", -1)
            if exit_code != 0 and not stderr:
                stderr = f"Process exited with code {exit_code}.\n{stdout}"

            return stdout.strip(), stderr.strip()

        except ContainerError as exc:
            logger.exception("Container error")
            return "", f"Container error: {exc}"
        except Exception as exc:
            logger.exception("Sandbox execution error")
            return "", f"Execution error: {exc}"
        finally:
            # Always clean up
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
