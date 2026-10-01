"""
Smoke test for the Ollama provider.

Prerequisites:
    1. Ollama running:   ollama serve
    2. Model pulled:     ollama pull llama3.2
    3. Embeddings:       ollama pull nomic-embed-text

Run:
    cd "e:\Data Assister"
    python -m backend.tests.test_ollama_provider
"""

import asyncio
import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Force Ollama provider for this test
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["EMBEDDING_PROVIDER"] = "ollama"


async def test_ollama_llm():
    """Test that Ollama LLM generates a response."""
    from backend.core import create_llm

    llm = create_llm("ollama")
    print(f"✅ Created LLM provider: {llm.model_name}")

    response = await llm.generate([
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say 'hello' in exactly one word."},
    ])

    print(f"✅ LLM response: {response.content!r}")
    print(f"   Model: {response.model}")
    print(f"   Usage: {response.usage}")
    print(f"   Finish: {response.finish_reason}")
    assert response.content, "LLM returned empty response"
    print("✅ LLM test PASSED\n")


async def test_ollama_llm_stream():
    """Test that Ollama LLM streams tokens."""
    from backend.core import create_llm

    llm = create_llm("ollama")
    print("Testing streaming...")

    tokens = []
    async for token in llm.generate_stream([
        {"role": "user", "content": "Count from 1 to 5."},
    ]):
        tokens.append(token)
        print(f"  token: {token!r}")

    full_text = "".join(tokens)
    print(f"✅ Streamed {len(tokens)} chunks, total: {len(full_text)} chars")
    assert full_text, "Streaming returned empty"
    print("✅ Streaming test PASSED\n")


async def test_ollama_embedder():
    """Test that Ollama generates embeddings."""
    from backend.core import create_embedder

    embedder = create_embedder("ollama")
    print(f"✅ Created embedder (expected dim: {embedder.dimension})")

    texts = [
        "Column 'revenue' — dtype: float64, mean: 1234.5",
        "Column 'customer_id' — dtype: int64, unique: 5000",
    ]
    vectors = await embedder.embed(texts)

    print(f"✅ Got {len(vectors)} vectors")
    print(f"   Dimension: {len(vectors[0])}")
    print(f"   First 5 values: {vectors[0][:5]}")
    assert len(vectors) == 2, f"Expected 2 vectors, got {len(vectors)}"
    assert len(vectors[0]) > 0, "Empty embedding vector"
    print("✅ Embedder test PASSED\n")


async def test_provider_switching():
    """Test that factory switching works."""
    from backend.core.llm import create_llm
    from backend.core.embedder import create_embedder

    # These should not crash (just instantiate)
    ollama_llm = create_llm("ollama")
    assert ollama_llm.model_name == "llama3.2"

    ollama_emb = create_embedder("ollama")
    assert ollama_emb.dimension > 0

    print("✅ Provider switching test PASSED\n")


async def main():
    print("=" * 60)
    print("  Ollama Provider Smoke Tests")
    print("=" * 60)
    print()

    await test_provider_switching()
    await test_ollama_llm()
    await test_ollama_llm_stream()
    await test_ollama_embedder()

    print("=" * 60)
    print("  ALL TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
