import logging
from typing import Generator, Optional, List
from app.core.config import settings

logger = logging.getLogger(__name__)
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


class LLMService:
    """
    Advanced Multi-Provider LLM Service.
    Supports:
    - Google Gemini (gemini-1.5-flash, gemini-2.0-flash, gemini-1.5-pro)
    - OpenAI (gpt-4o, gpt-4o-mini)
    - Groq (llama-3.3-70b-versatile)
    - Azure OpenAI
    - Zero-config deterministic Socratic fallback
    """

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.model = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self._gemini_client = None

    def _get_gemini_client(self):
        if self._gemini_client is None and settings.GEMINI_API_KEY:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
        return self._gemini_client

    def is_live_model_configured(self) -> bool:
        if self.provider == "gemini" and settings.GEMINI_API_KEY:
            return True
        if self.provider == "openai" and settings.OPENAI_API_KEY:
            return True
        if self.provider == "groq" and settings.GROQ_API_KEY:
            return True
        if self.provider == "azure_openai" and settings.AZURE_OPENAI_API_KEY:
            return True
        return False

    # ------------------------------------------------------------------
    # Internal: Gemini helpers with retry on empty-output error
    # ------------------------------------------------------------------

    def _gemini_candidate_models(self) -> List[str]:
        """Returns ordered list of Gemini fallback model names."""
        candidates = [self.model]
        for fb in [
            "gemini-3.8-flash",
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite",
            "gemini-3.6-flash",
            "gemini-flash-lite-latest",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
        ]:
            if fb not in candidates:
                candidates.append(fb)
        return candidates

    @staticmethod
    def _is_quota_or_unavailable_error(err_msg: str) -> bool:
        return any(
            k in err_msg
            for k in [
                "not found",
                "404",
                "no longer available",
                "429",
                "quota",
                "resource_exhausted",
                "503",
                "unavailable",
            ]
        )

    @staticmethod
    def _is_empty_output_error(err_msg: str) -> bool:
        return any(
            k in err_msg
            for k in [
                "model output",
                "must contain",
                "output text",
            ]
        )

    def _call_gemini(self, prompt: str, system_prompt: Optional[str]) -> Optional[str]:
        """
        Calls Gemini with up to 2 attempts and candidate model fallbacks.
        On 'model output must contain either output text or tool calls' (empty
        response due to safety / recitation block), retries by folding the system
        prompt into the user message so Gemini sees pure text content.
        """
        client = self._get_gemini_client()
        if not client:
            return None
        from google import genai
        current_prompt = prompt
        current_sys = system_prompt

        candidate_models = self._gemini_candidate_models()

        for model_name in candidate_models:
            for attempt in range(2):
                try:
                    config = (
                        genai.types.GenerateContentConfig(
                            system_instruction=current_sys,
                            temperature=self.temperature,
                        )
                        if current_sys
                        else genai.types.GenerateContentConfig(temperature=self.temperature)
                    )
                    response = client.models.generate_content(
                        model=model_name,
                        contents=current_prompt,
                        config=config,
                    )

                    # Check for safety/recitation blocks via finish_reason
                    if response.candidates:
                        candidate = response.candidates[0]
                        finish_reason = str(getattr(candidate, "finish_reason", "STOP"))
                        if finish_reason not in ("STOP", "FinishReason.STOP", "1"):
                            logger.warning(
                                f"Gemini finish_reason={finish_reason} on attempt {attempt + 1}."
                            )
                            if attempt == 0:
                                # fold system prompt into user message and retry
                                if current_sys:
                                    current_prompt = f"{current_sys}\n\n{prompt}"
                                    current_sys = None
                                continue
                            return None

                    if response and response.text:
                        return response.text

                    # Empty text but no block — retry once
                    logger.warning(f"Gemini returned empty text on attempt {attempt + 1}.")
                    if attempt == 0 and current_sys:
                        current_prompt = f"{current_sys}\n\n{prompt}"
                        current_sys = None

                except Exception as e:
                    err_msg = str(e).lower()
                    if self._is_quota_or_unavailable_error(err_msg):
                        logger.warning(f"Model {model_name} unavailable or quota limited: {e}. Trying next candidate model.")
                        break

                    if self._is_empty_output_error(err_msg) and attempt == 0:
                        logger.warning(
                            f"Gemini empty-output error (attempt {attempt + 1}): {e}. "
                            "Retrying with simplified prompt."
                        )
                        if current_sys:
                            current_prompt = f"{current_sys}\n\n{prompt}"
                            current_sys = None
                        continue
                    logger.error(f"Gemini LLM call failed on {model_name}: {e}")
                    break

        return None

    def _stream_gemini(
        self, prompt: str, system_prompt: Optional[str]
    ) -> Generator[str, None, None]:
        """
        Stream from Gemini; on empty-output / blocked response retries once
        with system prompt folded into user message.
        """
        client = self._get_gemini_client()
        if not client:
            return
        from google import genai
        current_prompt = prompt
        current_sys = system_prompt

        candidate_models = self._gemini_candidate_models()

        for model_name in candidate_models:
            for attempt in range(2):
                try:
                    config = (
                        genai.types.GenerateContentConfig(
                            system_instruction=current_sys,
                            temperature=self.temperature,
                        )
                        if current_sys
                        else genai.types.GenerateContentConfig(temperature=self.temperature)
                    )
                    yielded_any = False
                    for chunk in client.models.generate_content_stream(
                        model=model_name,
                        contents=current_prompt,
                        config=config,
                    ):
                        if chunk.text:
                            yield chunk.text
                            yielded_any = True

                    if yielded_any:
                        return

                    logger.warning(f"Gemini stream yielded nothing on attempt {attempt + 1}.")
                    if attempt == 0 and current_sys:
                        current_prompt = f"{current_sys}\n\n{prompt}"
                        current_sys = None

                except Exception as e:
                    err_msg = str(e).lower()
                    if self._is_quota_or_unavailable_error(err_msg):
                        logger.warning(f"Model {model_name} stream unavailable or quota limited: {e}. Trying fallback.")
                        break

                    if self._is_empty_output_error(err_msg) and attempt == 0:
                        logger.warning(
                            f"Gemini empty-output stream error (attempt {attempt + 1}): {e}. Retrying."
                        )
                        if current_sys:
                            current_prompt = f"{current_sys}\n\n{prompt}"
                            current_sys = None
                        continue
                    logger.error(f"Gemini streaming failed on {model_name}: {e}")
                    break

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generates a complete response using the configured LLM provider."""
        if not self.is_live_model_configured():
            return self._fallback_socratic_response(prompt)

        # 1. Google Gemini
        if self.provider == "gemini" and settings.GEMINI_API_KEY:
            result = self._call_gemini(prompt, system_prompt)
            if result:
                return result

        # 2. OpenAI or Groq
        if (self.provider == "openai" and settings.OPENAI_API_KEY) or (
            self.provider == "groq" and settings.GROQ_API_KEY
        ):
            try:
                import openai

                base_url = "https://api.groq.com/openai/v1" if self.provider == "groq" else None
                api_key = (
                    settings.GROQ_API_KEY if self.provider == "groq" else settings.OPENAI_API_KEY
                )
                client = openai.OpenAI(api_key=api_key, base_url=base_url)

                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                )
                if resp.choices and resp.choices[0].message.content:
                    return resp.choices[0].message.content
            except Exception as e:
                logger.error(
                    f"{self.provider.upper()} LLM call failed: {e}. Falling back to Socratic engine."
                )

        # 3. Azure OpenAI
        if self.provider == "azure_openai" and settings.AZURE_OPENAI_API_KEY:
            try:
                import openai

                client = openai.AzureOpenAI(
                    azure_endpoint=settings.AZURE_OPENAI_ENDPOINT or "",
                    api_key=settings.AZURE_OPENAI_API_KEY,
                    api_version="2024-02-15-preview",
                )
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                resp = client.chat.completions.create(
                    model=settings.AZURE_OPENAI_DEPLOYMENT_NAME or self.model,
                    messages=messages,
                    temperature=self.temperature,
                )
                if resp.choices and resp.choices[0].message.content:
                    return resp.choices[0].message.content
            except Exception as e:
                logger.error(f"Azure OpenAI LLM call failed: {e}.")

        return self._fallback_socratic_response(prompt)

    def stream_generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Streams tokens in real-time using the configured LLM provider."""
        if not self.is_live_model_configured():
            full_text = self._fallback_socratic_response(prompt)
            for word in full_text.split(" "):
                yield word + " "
            return

        # 1. Stream with Google Gemini (with retry on empty-output error)
        if self.provider == "gemini" and settings.GEMINI_API_KEY:
            yielded_any = False
            for token in self._stream_gemini(prompt, system_prompt):
                yield token
                yielded_any = True
            if yielded_any:
                return

        # 2. Stream with OpenAI / Groq
        if (self.provider == "openai" and settings.OPENAI_API_KEY) or (
            self.provider == "groq" and settings.GROQ_API_KEY
        ):
            try:
                import openai

                base_url = "https://api.groq.com/openai/v1" if self.provider == "groq" else None
                api_key = (
                    settings.GROQ_API_KEY if self.provider == "groq" else settings.OPENAI_API_KEY
                )
                client = openai.OpenAI(api_key=api_key, base_url=base_url)

                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                stream = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    stream=True,
                )
                yielded_any = False
                for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else ""
                    if delta:
                        yield delta
                        yielded_any = True
                if yielded_any:
                    return
            except Exception as e:
                logger.error(f"{self.provider.upper()} streaming failed: {e}")

        # 3. Azure OpenAI Streaming
        if self.provider == "azure_openai" and settings.AZURE_OPENAI_API_KEY:
            try:
                import openai

                client = openai.AzureOpenAI(
                    azure_endpoint=settings.AZURE_OPENAI_ENDPOINT or "",
                    api_key=settings.AZURE_OPENAI_API_KEY,
                    api_version="2024-02-15-preview",
                )
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                stream = client.chat.completions.create(
                    model=settings.AZURE_OPENAI_DEPLOYMENT_NAME or self.model,
                    messages=messages,
                    temperature=self.temperature,
                    stream=True,
                )
                yielded_any = False
                for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else ""
                    if delta:
                        yield delta
                        yielded_any = True
                if yielded_any:
                    return
            except Exception as e:
                logger.error(f"Azure OpenAI streaming failed: {e}")

        # Final fallback stream
        full_text = self._fallback_socratic_response(prompt)
        for word in full_text.split(" "):
            yield word + " "

    def _fallback_socratic_response(self, prompt: str) -> str:
        return (
            "I am currently reconnecting to the AI language model service. "
            "Please try submitting your question again in a moment, or select one of the suggested study questions below!"
        )


default_llm_service = LLMService()
