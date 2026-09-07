"""
Gemini Client Adapter delegating to unified OpenAI LLM client.
"""
from app.rag.llm_client import llm_client, LLMClient

gemini_client = llm_client
GeminiClient = LLMClient
