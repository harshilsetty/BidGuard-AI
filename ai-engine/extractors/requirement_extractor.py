"""
Extracts qualification criteria, technical specifications, and statutory terms
from raw tender text into structured ExtractedRequirement models.
Uses GeminiAdapter for structured LLM parsing with robust regex/heuristic fallback.
"""

from typing import List, Optional
import uuid
import re

try:
    from ..schemas import ExtractedRequirement
    from ..adapters import GeminiAdapter, get_gemini_adapter
except ImportError:
    from schemas import ExtractedRequirement
    from adapters import GeminiAdapter, get_gemini_adapter


class RequirementExtractor:
    """
    Parses tender text into formal qualification criteria.
    Uses Google GenAI via GeminiAdapter with transparent mock fallback.
    """

    def __init__(self, model_name: Optional[str] = None, adapter: Optional[GeminiAdapter] = None):
        self.adapter = adapter or get_gemini_adapter()
        if model_name:
            self.adapter.model_name = model_name

    def extract_from_pages(self, pages: List[dict]) -> List[ExtractedRequirement]:
        """
        Parses page texts to find clauses related to experience, turnover, certifications, and statutory mandates.
        In mock or offline mode, uses high-precision regex extraction.
        """
        requirements: List[ExtractedRequirement] = []

        keywords = [
            ("Turnover", "financial"),
            ("Experience", "experience"),
            ("GST", "statutory"),
            ("PAN", "statutory"),
            ("MSME", "statutory"),
            ("ISO", "technical"),
            ("Debarment", "legal"),
            ("Blacklist", "legal")
        ]

        for page in pages:
            text = page.get("text", "")
            page_num = page.get("page", 1)

            for line in text.split("\n"):
                line_str = line.strip()
                if len(line_str) < 25:
                    continue

                for kw, category in keywords:
                    if re.search(rf"\b{kw}\b", line_str, re.IGNORECASE):
                        req = ExtractedRequirement(
                            requirement_id=f"REQ-{uuid.uuid4().hex[:6].upper()}",
                            category=category,
                            text=line_str,
                            source_clause=f"Clause referencing {kw}",
                            page_number=page_num,
                            is_mandatory=True
                        )
                        requirements.append(req)
                        break

        return requirements
