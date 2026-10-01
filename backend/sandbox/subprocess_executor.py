"""
Subprocess Sandbox — local code execution for development.

Runs LLM-generated Python code in a subprocess with a timeout.
NOT secure for production — use the Docker sandbox for untrusted code.

This executor:
  • Creates a temp directory with the dataset
  • Rewrites sandbox paths in the code to local temp paths
  • Runs the script via ``subprocess`` with a timeout
  • Captures stdout, stderr, and any files written to the output dir
  • Cleans up the temp directory after execution

For production, use ``DockerSandbox`` which provides network isolation,
memory limits, and filesystem restrictions.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from backend.core.sandbox import ExecutionResult, SandboxProvider

logger = logging.getLogger(__name__)


class SubprocessSandbox(SandboxProvider):
    """
    Execute Python code in a local subprocess.

    ⚠️  Development only — no security isolation.
    """

    def __init__(self) -> None:
        from backend.config import settings
        self.timeout = settings.sandbox_timeout
        self._python = sys.executable  # Use the same Python interpreter

    @property
    def provider_name(self) -> str:
        return "subprocess"

    async def execute(
        self,
        code: str,
        dataset_path: str,
    ) -> ExecutionResult:
        """
        Execute code in a subprocess with the dataset available.

        The code is expected to reference ``/sandbox/data/dataset.csv``
        (the Docker convention).  We rewrite those paths to point at
        the real temp directory location.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run, code, dataset_path)

    # ── Private sync implementation ─────────────────────────────

    def _run(self, code: str, dataset_path: str) -> ExecutionResult:
        """Synchronous subprocess execution with temp-dir setup."""
        work_dir = None
        start_time = time.monotonic()

        try:
            # ── Set up working directory ──
            work_dir = Path(tempfile.mkdtemp(prefix="datasandbox_"))
            data_dir = work_dir / "data"
            output_dir = work_dir / "output"
            data_dir.mkdir()
            output_dir.mkdir()

            # Copy dataset into temp dir
            dataset_dest = data_dir / "dataset.csv"
            shutil.copy2(dataset_path, dataset_dest)

            # ── Rewrite sandbox paths to local paths ──
            # The LLM generates code referencing Docker sandbox paths.
            # We translate them to our temp directory.
            patched_code = self._rewrite_paths(
                code,
                dataset_dest=str(dataset_dest),
                output_dest=str(output_dir),
            )

            # Write script
            script_path = work_dir / "script.py"
            script_path.write_text(patched_code, encoding="utf-8")

            # ── Execute ──
            result = subprocess.run(
                [self._python, str(script_path)],
                capture_output=True,
                timeout=self.timeout,
                cwd=str(work_dir),
                env=self._build_env(),
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            # Collect artifacts (plots, output files)
            artifacts = self._collect_artifacts(output_dir)

            elapsed = time.monotonic() - start_time

            # Non-zero exit code without stderr → create error info
            if result.returncode != 0 and not stderr:
                stderr = f"Process exited with code {result.returncode}.\n{stdout}"

            return ExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=result.returncode,
                artifacts=artifacts,
                execution_time=elapsed,
            )

        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start_time
            return ExecutionResult(
                stderr=f"Execution timed out after {self.timeout} seconds.",
                exit_code=-1,
                execution_time=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - start_time
            logger.exception("Subprocess sandbox error")
            return ExecutionResult(
                stderr=f"Sandbox error: {exc}",
                exit_code=-1,
                execution_time=elapsed,
            )

        finally:
            # Clean up temp directory
            if work_dir is not None:
                try:
                    shutil.rmtree(work_dir, ignore_errors=True)
                except Exception:
                    pass

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _rewrite_paths(
        code: str,
        *,
        dataset_dest: str,
        output_dest: str,
    ) -> str:
        """
        Replace Docker sandbox paths with local temp paths.

        The LLM is instructed to use:
          • /sandbox/data/dataset.csv  → dataset file
          • /sandbox/output/           → artifact output directory

        We rewrite these to the actual temp directory locations.
        Uses forward slashes on Windows to avoid escape issues in Python strings.
        """
        # Normalise to forward slashes (safe in Python on all platforms)
        dataset_dest = dataset_dest.replace("\\", "/")
        output_dest = output_dest.replace("\\", "/")

        # Ensure output path ends with /
        if not output_dest.endswith("/"):
            output_dest += "/"

        patched = code.replace("/sandbox/data/dataset.csv", dataset_dest)
        patched = patched.replace("/sandbox/output/", output_dest)
        patched = patched.replace("/sandbox/output", output_dest.rstrip("/"))

        return patched

    @staticmethod
    def _collect_artifacts(output_dir: Path) -> dict[str, bytes]:
        """
        Walk the output directory and collect any files as binary artifacts.

        Returns a dict of ``{filename: bytes}``.
        """
        artifacts: dict[str, bytes] = {}

        if not output_dir.exists():
            return artifacts

        for file_path in output_dir.rglob("*"):
            if file_path.is_file():
                try:
                    rel_name = file_path.relative_to(output_dir).as_posix()
                    artifacts[rel_name] = file_path.read_bytes()
                except Exception as exc:
                    logger.warning(
                        "Failed to collect artifact %s: %s", file_path, exc
                    )

        return artifacts

    @staticmethod
    def _build_env() -> dict[str, str]:
        """
        Build a clean environment for the subprocess.

        Inherits the parent env (needed for Python to find its stdlib)
        but can be restricted further for security in future.
        """
        env = os.environ.copy()
        # Prevent the subprocess from importing the backend package
        env.pop("PYTHONPATH", None)
        # Ensure matplotlib uses non-interactive backend
        env["MPLBACKEND"] = "Agg"
        return env
