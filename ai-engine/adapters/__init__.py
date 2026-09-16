"""
AI Provider Adapters module for BidGuard.
Isolates external LLM provider SDKs (Google GenAI) behind a unified, testable interface.
"""

from .gemini_adapter import GeminiAdapter, get_gemini_adapter

__all__ = ["GeminiAdapter", "get_gemini_adapter"]
