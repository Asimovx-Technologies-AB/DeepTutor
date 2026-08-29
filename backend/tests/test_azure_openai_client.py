from types import SimpleNamespace

import pytest

from app.rag.azure_openai_client import AzureOpenAIClient


class _Embeddings:
    async def create(self, **kwargs):
        assert kwargs["dimensions"] == 1536
        assert kwargs["model"] == "text-embedding-3-small"
        return SimpleNamespace(data=[
            SimpleNamespace(index=1, embedding=[2.0]),
            SimpleNamespace(index=0, embedding=[1.0]),
        ])


class _Client:
    embeddings = _Embeddings()


@pytest.mark.asyncio
async def test_embedding_batch_preserves_input_order(monkeypatch):
    client = AzureOpenAIClient()
    monkeypatch.setattr(client, "_get_client", lambda: _Client())

    result = await client.embed_batch(["first", "second"])

    assert result == [[1.0], [2.0]]
