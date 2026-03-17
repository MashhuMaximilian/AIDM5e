import logging
import time
from pathlib import Path

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from config import (
    GEMINI_API_KEY,
    GEMINI_CHAT_MODEL,
    GEMINI_FALLBACK_MODEL,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_SUMMARY_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_TRANSCRIBE_MODEL,
    GEMINI_TOP_K,
    GEMINI_TOP_P,
)


logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self) -> None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        model_name: str | None = None,
    ) -> str:
        return self._generate_text_with_model(model_name or GEMINI_CHAT_MODEL, prompt, system_instruction)

    def generate_summary_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> str:
        return self._generate_text_with_model(GEMINI_SUMMARY_MODEL, prompt, system_instruction)

    def generate_text_from_files(
        self,
        file_paths: list[str],
        prompt: str,
        model_name: str | None = None,
    ) -> str:
        uploaded_files = [self.client.files.upload(file=Path(file_path)) for file_path in file_paths]
        chosen_model = model_name or GEMINI_SUMMARY_MODEL

        try:
            for index, uploaded in enumerate(uploaded_files):
                uploaded_files[index] = self._wait_for_file(uploaded)

            try:
                response = self.client.models.generate_content(
                    model=chosen_model,
                    contents=[prompt, *uploaded_files],
                )
            except ClientError as exc:
                status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                if status_code == 404 and chosen_model != GEMINI_FALLBACK_MODEL:
                    logger.warning("Gemini model %s unavailable for files; retrying with %s", chosen_model, GEMINI_FALLBACK_MODEL)
                    response = self.client.models.generate_content(
                        model=GEMINI_FALLBACK_MODEL,
                        contents=[prompt, *uploaded_files],
                    )
                else:
                    raise
            return (response.text or "").strip()
        finally:
            for uploaded in uploaded_files:
                try:
                    self.client.files.delete(name=uploaded.name)
                except Exception as exc:
                    logger.warning("Failed to delete uploaded Gemini file %s: %s", uploaded.name, exc)

    def _wait_for_file(self, uploaded):
        for _ in range(60):
            state = getattr(uploaded, "state", None)
            state_name = getattr(state, "name", None)
            if state_name in (None, "ACTIVE", "SUCCEEDED"):
                return uploaded
            if state_name == "FAILED":
                raise RuntimeError(f"Gemini file processing failed for {uploaded.name}.")
            time.sleep(1)
            uploaded = self.client.files.get(name=uploaded.name)
        return uploaded

    def generate_text_with_url_context(
        self,
        prompt: str,
        urls: list[str],
        system_instruction: str | None = None,
    ) -> str:
        joined_urls = "\n".join(f"- {url}" for url in urls)
        contextual_prompt = f"{prompt}\n\nRelevant public URLs:\n{joined_urls}"
        config = types.GenerateContentConfig(
            temperature=GEMINI_TEMPERATURE,
            top_p=GEMINI_TOP_P,
            top_k=GEMINI_TOP_K,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
            system_instruction=system_instruction,
            tools=[types.Tool(url_context=types.UrlContext())],
        )
        return self._generate_with_config(GEMINI_CHAT_MODEL, contextual_prompt, config)

    def _generate_text_with_model(self, model_name: str, prompt: str, system_instruction: str | None = None) -> str:
        config = types.GenerateContentConfig(
            temperature=GEMINI_TEMPERATURE,
            top_p=GEMINI_TOP_P,
            top_k=GEMINI_TOP_K,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
            system_instruction=system_instruction,
        )
        return self._generate_with_config(model_name, prompt, config)

    def _generate_with_config(self, model_name: str, prompt: str, config: types.GenerateContentConfig) -> str:
        try:
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
        except ClientError as exc:
            status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if status_code == 404 and model_name != GEMINI_FALLBACK_MODEL:
                logger.warning("Gemini model %s unavailable; retrying with %s", model_name, GEMINI_FALLBACK_MODEL)
                response = self.client.models.generate_content(
                    model=GEMINI_FALLBACK_MODEL,
                    contents=prompt,
                    config=config,
                )
            else:
                raise
        return (response.text or "").strip()

    def transcribe_audio(self, audio_file_path: str, prompt: str, model_name: str | None = None) -> str:
        uploaded = self.client.files.upload(file=Path(audio_file_path))
        chosen_model = model_name or GEMINI_TRANSCRIBE_MODEL

        uploaded = self._wait_for_file(uploaded)

        try:
            try:
                response = self.client.models.generate_content(
                    model=chosen_model,
                    contents=[prompt, uploaded],
                )
            except ClientError as exc:
                status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                if status_code == 404 and chosen_model != GEMINI_FALLBACK_MODEL:
                    logger.warning("Gemini model %s unavailable for audio; retrying with %s", chosen_model, GEMINI_FALLBACK_MODEL)
                    response = self.client.models.generate_content(
                        model=GEMINI_FALLBACK_MODEL,
                        contents=[prompt, uploaded],
                    )
                else:
                    raise
            return (response.text or "").strip()
        finally:
            try:
                self.client.files.delete(name=uploaded.name)
            except Exception as exc:
                logger.warning("Failed to delete uploaded Gemini file %s: %s", uploaded.name, exc)


gemini_client = GeminiClient()
