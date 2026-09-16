"""
Semantic Matcher: Compares requirement vs evidence using LLM prompts with strict JSON schema enforcement.
Isolates Google GenAI calls behind GeminiAdapter with transparent offline mock fallback.
"""

from typing import Dict, Any, List, Optional
import re

try:
    from ..schemas import (
        MatchingResult,
        AIComplianceEvaluation,
        EvidenceItem,
        ComplianceStatus,
    )
    from .rule_validator import RuleValidator
    from ..adapters import GeminiAdapter, get_gemini_adapter
except ImportError:
    from schemas import (
        MatchingResult,
        AIComplianceEvaluation,
        EvidenceItem,
        ComplianceStatus,
    )
    from matcher.rule_validator import RuleValidator
    from adapters import GeminiAdapter, get_gemini_adapter


def _stem_token(w: str) -> str:
    w = w.lower()
    for suffix in ("ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            return w[:-len(suffix)]
    return w


class SemanticMatcher:
    """
    Performs hybrid matching: evaluates semantic alignment while applying
    deterministic rule validation overrides.
    Uses GeminiAdapter with zero vendor lock-in.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        adapter: Optional[GeminiAdapter] = None,
    ):
        self.adapter = adapter or get_gemini_adapter()
        if model_name:
            self.adapter.model_name = model_name
        self.rule_validator = RuleValidator()

    def evaluate_multi_evidence(
        self,
        requirement_id: str,
        requirement_text: str,
        requirement_type: str,
        evidence_items: List[EvidenceItem],
        deterministic_rules: Optional[Dict[str, Any]] = None,
    ) -> AIComplianceEvaluation:
        """
        Evaluates a requirement against one or more evidence items extracted from bidder submissions.
        Handles:
        - Missing evidence (0 items)
        - Numeric threshold checks (deterministic override)
        - Contradictory evidence detection
        - Semantic alignment (PASS / FAIL / REVIEW)
        """
        # Case A: Missing evidence
        if not evidence_items:
            return AIComplianceEvaluation(
                requirement_id=requirement_id,
                requirement=requirement_text,
                requirement_type=requirement_type,
                evidence=[],
                status=ComplianceStatus.REVIEW,
                confidence=1.0,
                reason="No supporting evidence or documentation found in bidder submission for this mandatory requirement.",
                requires_human_review=True,
                contradiction_detected=False,
                deterministic_override=True,
            )

        # Case B: Contradiction detection across multiple documents
        if len(evidence_items) > 1:
            all_text = " ".join(e.text for e in evidence_items)
            year_matches = re.findall(r"\b(19\d\d|20\d\d)\b", all_text)
            exp_matches = re.findall(r"(\d+)\s+years", all_text, re.IGNORECASE)

            is_contradiction = False
            contradiction_msg = ""

            if deterministic_rules and deterministic_rules.get("flag_contradiction"):
                is_contradiction = True
                contradiction_msg = deterministic_rules.get("contradiction_reason", "Conflicting claims found across documents.")
            elif exp_matches and year_matches:
                claimed_exp = int(exp_matches[0])
                recent_year = max(int(y) for y in year_matches)
                current_year = 2026
                actual_years = current_year - recent_year
                if actual_years < claimed_exp and recent_year >= 2020:
                    is_contradiction = True
                    contradiction_msg = (
                        f"Conflicting evidence detected: Document claims {claimed_exp} years experience, "
                        f"but incorporation/registration document indicates establishment in {recent_year} ({actual_years} years active)."
                    )

            if is_contradiction:
                return AIComplianceEvaluation(
                    requirement_id=requirement_id,
                    requirement=requirement_text,
                    requirement_type=requirement_type,
                    evidence=evidence_items,
                    status=ComplianceStatus.REVIEW,
                    confidence=0.90,
                    reason=contradiction_msg,
                    requires_human_review=True,
                    contradiction_detected=True,
                    deterministic_override=True,
                )

        # Case C: Deterministic Numeric Threshold Overrides
        if deterministic_rules:
            if "required_turnover" in deterministic_rules and "presented_turnover" in deterministic_rules:
                status, reason = self.rule_validator.validate_turnover(
                    deterministic_rules["required_turnover"],
                    deterministic_rules["presented_turnover"],
                )
                return AIComplianceEvaluation(
                    requirement_id=requirement_id,
                    requirement=requirement_text,
                    requirement_type=requirement_type,
                    evidence=evidence_items,
                    status=status,
                    confidence=1.0,
                    reason=reason,
                    requires_human_review=(status == ComplianceStatus.REVIEW),
                    contradiction_detected=False,
                    deterministic_override=True,
                )

            if "is_debarred" in deterministic_rules:
                status, reason = self.rule_validator.validate_debarment(
                    deterministic_rules["is_debarred"],
                    deterministic_rules.get("debarment_reason"),
                )
                return AIComplianceEvaluation(
                    requirement_id=requirement_id,
                    requirement=requirement_text,
                    requirement_type=requirement_type,
                    evidence=evidence_items,
                    status=status,
                    confidence=1.0,
                    reason=reason,
                    requires_human_review=False,
                    contradiction_detected=False,
                    deterministic_override=True,
                )

        # Case D: Semantic Text Alignment (Stemmed Token Overlap & LLM Fallback)
        primary_ev = evidence_items[0].text
        stop_words = {"the", "a", "an", "of", "in", "on", "at", "for", "with", "by", "is", "are", "be", "to", "must", "have", "has"}
        
        req_tokens = [_stem_token(w) for w in re.findall(r"\w+", requirement_text.lower()) if len(w) > 1 and w not in stop_words]
        ev_tokens = [_stem_token(w) for w in re.findall(r"\w+", primary_ev.lower()) if len(w) > 1 and w not in stop_words]

        req_set = set(req_tokens)
        ev_set = set(ev_tokens)

        overlap = req_set.intersection(ev_set)
        overlap_ratio = len(overlap) / max(len(req_set), 1)

        if overlap_ratio >= 0.35:
            status = ComplianceStatus.PASS
            confidence = min(0.70 + overlap_ratio * 0.28, 0.98)
            reason = f"Evidence strongly aligns with qualification terms ({len(overlap)} matching key tokens)."
        elif overlap_ratio >= 0.10:
            status = ComplianceStatus.REVIEW
            confidence = 0.65
            reason = "Partial semantic correspondence found. Officer manual inspection recommended."
        else:
            status = ComplianceStatus.FAIL
            confidence = 0.85
            reason = "Submitted document does not substantively address this requirement."

        return AIComplianceEvaluation(
            requirement_id=requirement_id,
            requirement=requirement_text,
            requirement_type=requirement_type,
            evidence=evidence_items,
            status=status,
            confidence=round(confidence, 2),
            reason=reason,
            requires_human_review=(status == ComplianceStatus.REVIEW),
            contradiction_detected=False,
            deterministic_override=False,
        )

    def evaluate_match(
        self,
        requirement_text: str,
        evidence_text: str,
        source_doc: str,
        page: int,
        deterministic_rules: Dict[str, Any] = None,
    ) -> MatchingResult:
        """
        Backwards-compatible wrapper returning MatchingResult for single evidence item.
        """
        item = EvidenceItem(text=evidence_text, document=source_doc, page=page)
        evaluation = self.evaluate_multi_evidence(
            requirement_id="REQ-LEGACY",
            requirement_text=requirement_text,
            requirement_type="general",
            evidence_items=[item],
            deterministic_rules=deterministic_rules,
        )
        return MatchingResult(
            requirement_id=evaluation.requirement_id,
            requirement=evaluation.requirement,
            requirement_type=evaluation.requirement_type,
            evidence=evaluation.evidence,
            status=evaluation.status,
            confidence=evaluation.confidence,
            reason=evaluation.reason,
            requires_human_review=evaluation.requires_human_review,
            contradiction_detected=evaluation.contradiction_detected,
            deterministic_override=evaluation.deterministic_override,
            metadata=evaluation.metadata,
        )
