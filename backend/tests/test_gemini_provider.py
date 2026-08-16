import pytest
import asyncio
from app.core.config import get_settings
from app.rag.gemini_client import GeminiClient
from app.rag.ollama_client import UnifiedLLMClient, ollama

def test_gemini_message_formatting():
    client = GeminiClient()
    messages = [
        {"role": "system", "content": "You are DeepTutor."},
        {"role": "user", "content": "Explain photosynthesis."},
        {"role": "assistant", "content": "Photosynthesis is the process..."},
        {"role": "user", "content": "Give an analogy."},
    ]
    formatted = client._format_messages_for_gemini(messages)
    assert "system_instruction" in formatted
    assert formatted["system_instruction"]["parts"][0]["text"] == "You are DeepTutor."
    assert len(formatted["contents"]) == 3
    assert formatted["contents"][0]["role"] == "user"
    assert formatted["contents"][0]["parts"][0]["text"] == "Explain photosynthesis."
    assert formatted["contents"][1]["role"] == "model"
    assert formatted["contents"][1]["parts"][0]["text"] == "Photosynthesis is the process..."
    assert formatted["contents"][2]["role"] == "user"
    assert formatted["contents"][2]["parts"][0]["text"] == "Give an analogy."

@pytest.mark.asyncio
async def test_unified_client_routing():
    unified = UnifiedLLMClient()
    # If no key set, is_available checks key
    assert isinstance(unified.provider, str)
    model = await unified.get_working_chat_model()
    assert "gemini" in model.lower() or "llama" in model.lower()
