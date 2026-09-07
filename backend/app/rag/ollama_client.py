"""
Unified LLM Client Adapter for OpenAI ChatGPT.
Maintains backward compatibility with legacy imports while delegating to the unified LLMClient.
"""
from app.rag.llm_client import llm_client, LLMClient

# Re-export singleton under legacy names for seamless compatibility
ollama = llm_client
gemini_client = llm_client
GeminiClient = LLMClient
