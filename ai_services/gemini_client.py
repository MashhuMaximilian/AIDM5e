import logging
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from config import (
    GEMINI_API_KEY,
    GEMINI_CHAT_MODEL,
    GEMINI_FALLBACK_MODEL,
    GEMINI_IMAGE_DEFAULT_ASPECT_RATIO,
    GEMINI_IMAGE_MODEL,
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

    def generate_text_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        model_name: str | None = None,
    ):
        yield from self._generate_text_stream_with_model(model_name or GEMINI_CHAT_MODEL, prompt, system_instruction)

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

    def generate_text_with_url_context_stream(
        self,
        prompt: str,
        urls: list[str],
        system_instruction: str | None = None,
    ):
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
        yield from self._generate_stream_with_config(GEMINI_CHAT_MODEL, contextual_prompt, config)

    def _generate_text_with_model(self, model_name: str, prompt: str, system_instruction: str | None = None) -> str:
        config = types.GenerateContentConfig(
            temperature=GEMINI_TEMPERATURE,
            top_p=GEMINI_TOP_P,
            top_k=GEMINI_TOP_K,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
            system_instruction=system_instruction,
        )
        return self._generate_with_config(model_name, prompt, config)

    def _generate_text_stream_with_model(self, model_name: str, prompt: str, system_instruction: str | None = None):
        config = types.GenerateContentConfig(
            temperature=GEMINI_TEMPERATURE,
            top_p=GEMINI_TOP_P,
            top_k=GEMINI_TOP_K,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
            system_instruction=system_instruction,
        )
        yield from self._generate_stream_with_config(model_name, prompt, config)

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

    def _generate_stream_with_config(self, model_name: str, prompt: str, config: types.GenerateContentConfig):
        try:
            stream = self.client.models.generate_content_stream(
                model=model_name,
                contents=prompt,
                config=config,
            )
            yield from self._yield_stream_text(stream)
        except ClientError as exc:
            status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if status_code == 404 and model_name != GEMINI_FALLBACK_MODEL:
                logger.warning("Gemini model %s unavailable for streaming; retrying with %s", model_name, GEMINI_FALLBACK_MODEL)
                stream = self.client.models.generate_content_stream(
                    model=GEMINI_FALLBACK_MODEL,
                    contents=prompt,
                    config=config,
                )
                yield from self._yield_stream_text(stream)
            else:
                raise

    @staticmethod
    def _yield_stream_text(stream):
        accumulated = ""
        for chunk in stream:
            text = (getattr(chunk, "text", None) or "").strip()
            if not text:
                continue
            if accumulated and text.startswith(accumulated):
                delta = text[len(accumulated):]
                accumulated = text
            else:
                delta = text
                accumulated += text
            if delta:
                yield delta

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

    def _load_image_bytes(self, source) -> tuple[bytes, str | None]:
        if hasattr(source, "image_bytes") and getattr(source, "image_bytes"):
            mime_type = getattr(source, "content_type", None) or "image/png"
            return getattr(source, "image_bytes"), mime_type

        if isinstance(source, (str, Path)):
            source_path = Path(source).expanduser()
            if source_path.exists():
                suffix = source_path.suffix.lower()
                mime_type = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                }.get(suffix, "image/png")
                return source_path.read_bytes(), mime_type

            request = Request(str(source), headers={"User-Agent": "AIDM/1.0"})
            with urlopen(request, timeout=30) as response:
                data = response.read()
                mime_type = response.headers.get_content_type()
                return data, mime_type

        if hasattr(source, "url"):
            urls = [getattr(source, "url", None), getattr(source, "proxy_url", None)]
            last_error = None
            for candidate_url in urls:
                if not candidate_url:
                    continue
                try:
                    request = Request(str(candidate_url), headers={"User-Agent": "AIDM/1.0"})
                    with urlopen(request, timeout=30) as response:
                        data = response.read()
                        mime_type = response.headers.get_content_type()
                        return data, mime_type
                except Exception as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error

        if isinstance(source, dict) and source.get("image_bytes"):
            return source["image_bytes"], source.get("content_type") or "image/png"

        if isinstance(source, dict) and (source.get("url") or source.get("proxy_url")):
            last_error = None
            for candidate_url in (source.get("url"), source.get("proxy_url")):
                if not candidate_url:
                    continue
                try:
                    request = Request(str(candidate_url), headers={"User-Agent": "AIDM/1.0"})
                    with urlopen(request, timeout=30) as response:
                        data = response.read()
                        mime_type = response.headers.get_content_type()
                        return data, mime_type
                except Exception as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error

        raise ValueError(f"Unsupported image source: {source!r}")

    def generate_image(
        self,
        prompt: str,
        *,
        model_name: str | None = None,
        aspect_ratio: str | None = None,
        reference_images: list | None = None,
        negative_prompt: str | None = None,
        number_of_images: int = 1,
    ) -> list[dict]:
        chosen_model = model_name or GEMINI_IMAGE_MODEL
        refs = list(reference_images or [])
        use_generate_content = chosen_model.startswith("gemini-")
        effective_prompt = prompt.strip()
        if negative_prompt:
            effective_prompt = (
                f"{effective_prompt}\n\n"
                f"Negative guidance: {negative_prompt.strip()}"
            ).strip()

        try:
            if use_generate_content:
                content_parts = [effective_prompt]
                for item in refs:
                    try:
                        image_bytes, mime_type = self._load_image_bytes(item)
                    except Exception as exc:
                        logger.warning("Skipping unusable reference image %r: %s", item, exc)
                        continue
                    content_parts.append(
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type=mime_type or "image/png",
                        )
                    )

                response = self.client.models.generate_content(
                    model=chosen_model,
                    contents=content_parts,
                    config=types.GenerateContentConfig(
                        candidate_count=number_of_images,
                        response_modalities=["TEXT", "IMAGE"],
                        image_config=types.ImageConfig(
                            aspect_ratio=aspect_ratio or GEMINI_IMAGE_DEFAULT_ASPECT_RATIO,
                        ),
                    ),
                )
                generated = []
                response_parts = getattr(response, "parts", None)
                if response_parts is None:
                    response_parts = []
                    for candidate in getattr(response, "candidates", []) or []:
                        content = getattr(candidate, "content", None)
                        response_parts.extend(getattr(content, "parts", []) or [])
                for part in response_parts:
                    inline_data = getattr(part, "inline_data", None)
                    image_bytes = getattr(inline_data, "data", None) if inline_data else None
                    mime_type = getattr(inline_data, "mime_type", None) if inline_data else None
                    if not image_bytes:
                        continue
                    generated.append(
                        {
                            "image_bytes": image_bytes,
                            "mime_type": mime_type or "image/png",
                            "enhanced_prompt": None,
                            "rai_filtered_reason": None,
                        }
                    )
            else:
                config = types.GenerateImagesConfig(
                    number_of_images=number_of_images,
                    aspect_ratio=aspect_ratio or GEMINI_IMAGE_DEFAULT_ASPECT_RATIO,
                    negative_prompt=negative_prompt,
                    output_mime_type="image/png",
                    add_watermark=False,
                )
                if refs:
                    logger.warning(
                        "Reference images are not supported for non-Gemini image generation path; using prompt-only generation."
                    )
                response = self.client.models.generate_images(
                    model=chosen_model,
                    prompt=effective_prompt,
                    config=config,
                )
                generated = getattr(response, "generated_images", None) or []
        except ClientError as exc:
            raise RuntimeError(f"Gemini image generation failed: {exc}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not fetch reference image: {exc}") from exc

        outputs: list[dict] = []
        for generated_image in generated:
            if isinstance(generated_image, dict):
                image_bytes = generated_image.get("image_bytes")
                mime_type = generated_image.get("mime_type")
                if not image_bytes:
                    continue
                outputs.append(
                    {
                        "image_bytes": image_bytes,
                        "mime_type": mime_type or "image/png",
                        "enhanced_prompt": generated_image.get("enhanced_prompt"),
                        "rai_filtered_reason": generated_image.get("rai_filtered_reason"),
                    }
                )
                continue
            image = getattr(generated_image, "image", None)
            image_bytes = getattr(image, "image_bytes", None) if image else None
            mime_type = getattr(image, "mime_type", None) if image else None
            if not image_bytes:
                continue
            outputs.append(
                {
                    "image_bytes": image_bytes,
                    "mime_type": mime_type or "image/png",
                    "enhanced_prompt": getattr(generated_image, "enhanced_prompt", None),
                    "rai_filtered_reason": getattr(generated_image, "rai_filtered_reason", None),
                }
            )
        return outputs


gemini_client = GeminiClient()
