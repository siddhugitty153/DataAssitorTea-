"""
Sandbox execution package.

Provides pluggable code execution backends:
  • SubprocessSandbox  — local subprocess (development)
  • DockerSandbox      — ephemeral Docker containers (production)

Use ``create_sandbox()`` from ``backend.core`` to get the right one
based on configuration.
"""

from backend.sandbox.subprocess_executor import SubprocessSandbox

# DockerSandbox requires the `docker` package — import lazily to avoid
# crashing when Docker is not installed (e.g. local dev without Docker Desktop).
try:
    from backend.sandbox.docker_executor import DockerSandbox
except ImportError:
    DockerSandbox = None  # type: ignore[assignment,misc]

__all__ = ["SubprocessSandbox", "DockerSandbox"]
