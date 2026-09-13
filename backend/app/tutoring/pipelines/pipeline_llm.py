"""
pipeline_llm.py
===============
Shared LLM helper for all tutoring pipelines.
Provides a single `call_pipeline_llm` function that calls the configured LLM
(via `default_llm_service`) with retry logic on empty output, and invokes a
provided fallback callable when the LLM is unavailable or returns nothing.
"""

import logging
from typing import Callable, Optional
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)


def call_pipeline_llm(
    system_prompt: str,
    user_prompt: str,
    fallback_fn: Callable[[], str],
    min_chars: int = 80,
) -> str:
    """
    Calls the live LLM with system_prompt + user_prompt.
    Returns the LLM response string if it meets `min_chars`.
    Falls back to `fallback_fn()` if the LLM is unconfigured, returns an
    empty/short response, or raises an exception.

    Args:
        system_prompt: Role/contract instructions for the LLM.
        user_prompt: The actual task content (context + query).
        fallback_fn: Zero-argument callable that produces a fallback string.
        min_chars: Minimum character length to accept an LLM response.

    Returns:
        A non-empty string response (LLM-generated or fallback).
    """
    if default_llm_service.is_live_model_configured():
        try:
            result = default_llm_service.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
            )
            if result and len(result.strip()) >= min_chars:
                return result.strip()
            logger.warning(
                "Pipeline LLM returned empty/short response; falling back."
            )
        except Exception as e:
            logger.error(f"Pipeline LLM call failed: {e}; falling back.")

    return fallback_fn()
