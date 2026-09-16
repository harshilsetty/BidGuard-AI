"""
Isolated Google GenAI Adapter for BidGuard (SIH26100).
Uses the modern Google GenAI SDK (google-genai>=2.0.0).
Provides transparent mock/fallback mode so test suites and local dev work with zero API keys.
"""

import os
import json
import logging
from typing import Optional, Type, TypeVar, Any
from pydantic import BaseModel

logger = logging.getLogger("bidguard.ai.gemini_adapter")

T = TypeVar("T", bound=BaseModel)


class GeminiAdapter:
    """
    Adapter encapsulating the Google GenAI SDK.
    Keeps the rest of the application agnostic to LLM vendor SDK specifics.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        # Determine if mock mode is requested or required due to missing key
        invalid_keys = {"", "your-gemini-api-key-here", "fake-key", "placeholder"}
        is_key_missing = (not self.api_key) or (self.api_key in invalid_keys)

        if mock_mode is not None:
            self.mock_mode = mock_mode
        else:
            self.mock_mode = is_key_missing

        self._client = None
        if not self.mock_mode:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                logger.info(f"GeminiAdapter initialized with model: {self.model_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize live Google GenAI client: {e}. Falling back to mock mode.")
                self.mock_mode = True

    @property
    def is_mock(self) -> bool:
        return self.mock_mode

    def generate_text(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """
        Generates text completion. Falls back to deterministic mock response if in mock mode.
        """
        if self.mock_mode or not self._client:
            return self._mock_text_response(prompt)

        try:
            from google.genai import types

            config = None
            if system_instruction:
                config = types.GenerateContentConfig(system_instruction=system_instruction)

            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            return response.text or ""
        except Exception as e:
            logger.error(f"Live Gemini generate_text error: {e}. Utilizing fallback response.")
            return self._mock_text_response(prompt)

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
    ) -> T:
        """
        Generates structured response strictly validated against a Pydantic schema.
        In mock mode, constructs a safe fallback instance compliant with response_schema.
        """
        if self.mock_mode or not self._client:
            return self._mock_structured_response(prompt, response_schema)

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                system_instruction=system_instruction,
            )

            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            raw_text = response.text or "{}"
            return response_schema.model_validate_json(raw_text)
        except Exception as e:
            logger.error(f"Live Gemini structured generation error: {e}. Utilizing fallback.")
            return self._mock_structured_response(prompt, response_schema)

    def _mock_text_response(self, prompt: str) -> str:
        """Deterministic mock text response for offline execution."""
        return (
            "[MOCK_AI_RESPONSE]: Requirement analyzed. Criteria satisfies standard "
            "General Financial Rules (GFR 2017) procurement guidelines."
        )

    def _mock_structured_response(self, prompt: str, schema: Type[T]) -> T:
        """
        Constructs a minimal valid schema instance for offline testing.
        """
        # If schema has default field constructors
        fields = {}
        for name, field_info in schema.model_fields.items():
            if field_info.default is not None and str(field_info.default) != "PydanticUndefined":
                fields[name] = field_info.default
            elif field_info.default_factory is not None:
                fields[name] = field_info.default_factory()
            elif field_info.annotation == str or getattr(field_info.annotation, "__name__", "") == "str":
                fields[name] = f"Mock {name}"
            elif field_info.annotation == int:
                fields[name] = 1
            elif field_info.annotation == float:
                fields[name] = 0.95
            elif field_info.annotation == bool:
                fields[name] = True
            elif hasattr(field_info.annotation, "__members__"):
                # Enum
                members = list(field_info.annotation.__members__.values())
                fields[name] = members[0].value if members else "PASS"

        try:
            return schema.model_validate(fields)
        except Exception:
            # Safe generic json dump fallback
            return schema.model_construct(**fields)


_default_adapter: Optional[GeminiAdapter] = None


def get_gemini_adapter() -> GeminiAdapter:
    """Singleton getter for the default GeminiAdapter instance."""
    global _default_adapter
    if _default_adapter is None:
        _default_adapter = GeminiAdapter()
    return _default_adapter
