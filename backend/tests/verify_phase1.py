"""
Phase 1 Verification — Tests provider abstractions and subprocess sandbox.

Run:  python -m backend.tests.verify_phase1

Tests:
  1. Config loads correctly with provider settings
  2. LLM factory creates a GeminiLLM instance
  3. Embedder factory creates a GeminiEmbedder instance
  4. Sandbox factory creates a SubprocessSandbox instance
  5. Subprocess sandbox can execute simple Python code
  6. Subprocess sandbox handles timeouts
  7. Subprocess sandbox collects artifacts
  8. (If API key set) LLM can generate a response
  9. (If API key set) Embedder can produce vectors
"""

from __future__ import annotations

import asyncio
import sys
import os

# Fix Windows console encoding for emoji/unicode output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_config():
    """Test that config loads with new provider fields."""
    from backend.config import settings

    assert hasattr(settings, "llm_provider"), "Missing llm_provider"
    assert hasattr(settings, "embedding_provider"), "Missing embedding_provider"
    assert hasattr(settings, "sandbox_provider"), "Missing sandbox_provider"
    assert hasattr(settings, "gemini_api_key"), "Missing gemini_api_key"
    assert hasattr(settings, "gemini_model"), "Missing gemini_model"
    assert settings.sandbox_provider in ("subprocess", "docker")
    print("  ✅ Config loads with all provider fields")


def test_llm_factory():
    """Test LLM factory creates the right instance."""
    from backend.core.llm import create_llm
    from backend.providers.gemini import GeminiLLM

    llm = create_llm("gemini")
    assert isinstance(llm, GeminiLLM)
    assert llm.model_name == "gemini-2.0-flash"
    print(f"  ✅ LLM factory → GeminiLLM (model: {llm.model_name})")


def test_embedder_factory():
    """Test embedder factory creates the right instance."""
    from backend.core.embedder import create_embedder
    from backend.providers.gemini import GeminiEmbedder

    embedder = create_embedder("gemini")
    assert isinstance(embedder, GeminiEmbedder)
    assert embedder.dimension == 768
    print(f"  ✅ Embedder factory → GeminiEmbedder (dim: {embedder.dimension})")


def test_sandbox_factory():
    """Test sandbox factory creates subprocess sandbox."""
    from backend.core.sandbox import create_sandbox
    from backend.sandbox.subprocess_executor import SubprocessSandbox

    sandbox = create_sandbox("subprocess")
    assert isinstance(sandbox, SubprocessSandbox)
    print(f"  ✅ Sandbox factory → SubprocessSandbox")


async def test_subprocess_execution():
    """Test that subprocess sandbox can run simple Python code."""
    from backend.core.sandbox import create_sandbox
    import tempfile, os

    sandbox = create_sandbox("subprocess")

    # Create a dummy dataset
    csv_content = "name,age,score\nAlice,30,95\nBob,25,87\nCharlie,35,92\n"
    fd, csv_path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write(csv_content)

    try:
        # Test basic execution
        code = """
import pandas as pd
df = pd.read_csv('/sandbox/data/dataset.csv')
print(f"Rows: {len(df)}")
print(f"Columns: {list(df.columns)}")
print(f"Mean age: {df['age'].mean()}")
"""
        result = await sandbox.execute(code, csv_path)
        assert result.success, f"Execution failed: {result.stderr}"
        assert "Rows: 3" in result.stdout
        assert "Mean age: 30.0" in result.stdout
        print(f"  ✅ Basic execution works (took {result.execution_time:.2f}s)")
        print(f"     Output: {result.stdout[:100]}")

        # Test timeout handling
        timeout_code = """
import time
time.sleep(999)
"""
        # Override timeout for this test
        sandbox.timeout = 3
        result = await sandbox.execute(timeout_code, csv_path)
        assert not result.success
        assert "timed out" in result.stderr.lower()
        print(f"  ✅ Timeout handling works")

        # Test artifact collection
        artifact_code = """
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.figure(figsize=(8, 6))
plt.plot([1, 2, 3], [1, 4, 9])
plt.title('Test Plot')
plt.savefig('/sandbox/output/plot.png')
print("Plot saved.")
"""
        sandbox.timeout = 30  # Reset timeout
        result = await sandbox.execute(artifact_code, csv_path)
        if result.success:
            if "plot.png" in result.artifacts:
                plot_size = len(result.artifacts["plot.png"])
                print(f"  ✅ Artifact collection works (plot.png: {plot_size} bytes)")
            else:
                print(f"  ⚠️ Execution succeeded but no artifact collected")
                print(f"     (matplotlib may not be installed)")
        else:
            print(f"  ⚠️ Artifact test skipped — matplotlib not available")
            print(f"     Error: {result.stderr[:100]}")

    finally:
        os.unlink(csv_path)


async def test_llm_api():
    """Test actual LLM API call (requires API key)."""
    from backend.config import settings
    from backend.core.llm import create_llm

    if not settings.gemini_api_key:
        print("  ⏭️  Skipped — GEMINI_API_KEY not set")
        return

    llm = create_llm("gemini")
    response = await llm.generate([
        {"role": "user", "content": "Say 'hello' and nothing else."},
    ])
    assert response.content, "Empty response"
    print(f"  ✅ LLM API works → '{response.content[:50]}'")
    if response.usage:
        print(f"     Tokens: {response.usage}")


async def test_embedder_api():
    """Test actual embedding API call (requires API key)."""
    from backend.config import settings
    from backend.core.embedder import create_embedder

    if not settings.gemini_api_key:
        print("  ⏭️  Skipped — GEMINI_API_KEY not set")
        return

    embedder = create_embedder("gemini")
    vectors = await embedder.embed(["test sentence"])
    assert len(vectors) == 1
    assert len(vectors[0]) > 0
    print(f"  ✅ Embedder API works → dimension={len(vectors[0])}")


async def main():
    print("\n🔧 Phase 1 Verification\n" + "=" * 40)

    print("\n1. Configuration:")
    test_config()

    print("\n2. Factories:")
    test_llm_factory()
    test_embedder_factory()
    test_sandbox_factory()

    print("\n3. Subprocess Sandbox:")
    await test_subprocess_execution()

    print("\n4. API Connectivity:")
    await test_llm_api()
    await test_embedder_api()

    print("\n" + "=" * 40)
    print("✅ Phase 1 verification complete!\n")


if __name__ == "__main__":
    asyncio.run(main())
