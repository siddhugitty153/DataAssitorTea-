"""
Sandbox Provider Abstraction.

Defines the interface for code execution backends.  LLM-generated code
is executed in a sandbox (Docker container, subprocess, cloud service)
and the result — stdout, stderr, and any produced artifacts — is
returned through a standard ``ExecutionResult``.

Usage:
    from backend.core import create_sandbox

    sandbox = create_sandbox("subprocess")
    result = await sandbox.execute(code, "/path/to/dataset.csv")
    print(result.stdout)
    for name, data in result.artifacts.items():
        print(f"Artifact: {name}, size: {len(data)} bytes")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ────────────────────────────────────────────────────────────────
# Data classes
# ────────────────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    """
    Standardised result from any sandbox execution.

    Attributes:
        stdout:          Captured standard output.
        stderr:          Captured standard error (non-empty ⟹ failure).
        exit_code:       Process exit code (0 ⟹ success).
        artifacts:       Named binary artifacts produced by the code
                         (e.g. ``{"plot.png": b"\\x89PNG..."}``)
        execution_time:  Wall-clock seconds the execution took.
    """

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    artifacts: dict[str, bytes] = field(default_factory=dict)
    execution_time: float = 0.0

    @property
    def success(self) -> bool:
        """True when exit code is 0 and stderr is empty."""
        return self.exit_code == 0 and not self.stderr


# ────────────────────────────────────────────────────────────────
# Abstract base
# ────────────────────────────────────────────────────────────────

class SandboxProvider(ABC):
    """
    Provider-agnostic interface for secure code execution.

    Concrete providers (Docker, subprocess, E2B, Modal, …)
    must implement ``execute``.

    The contract:
      • ``code`` is a complete, self-contained Python script.
      • The dataset is accessible at a path the provider manages.
      • The provider returns stdout, stderr, any saved files, and timing.
      • Providers MUST enforce a timeout.
    """

    @abstractmethod
    async def execute(
        self,
        code: str,
        dataset_path: str,
    ) -> ExecutionResult:
        """
        Execute a Python script with access to the given dataset.

        Args:
            code:         Complete Python script (string).
            dataset_path: Absolute path to the CSV on the host filesystem.

        Returns:
            ExecutionResult with stdout, stderr, artifacts, and timing.
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of this sandbox backend."""


# ────────────────────────────────────────────────────────────────
# Factory
# ────────────────────────────────────────────────────────────────

def create_sandbox(provider: str | None = None) -> SandboxProvider:
    """
    Create a sandbox provider instance.

    Args:
        provider: One of 'subprocess', 'docker'.
                  If None, reads from ``settings.sandbox_provider``.

    Returns:
        A concrete SandboxProvider.

    Raises:
        ValueError: If the provider is unknown.
    """
    if provider is None:
        from backend.config import settings
        provider = settings.sandbox_provider

    if provider == "subprocess":
        from backend.sandbox.subprocess_executor import SubprocessSandbox
        return SubprocessSandbox()

    if provider == "docker":
        from backend.sandbox.docker_executor import DockerSandbox
        return DockerSandbox()

    raise ValueError(
        f"Unknown sandbox provider '{provider}'. "
        f"Supported: 'subprocess', 'docker'."
    )
