"""
Deterministic Rule Validator: Governs strict compliance thresholds.
Deterministic business rules ALWAYS override probabilistic model predictions.
"""

from typing import Tuple, Optional
import re

try:
    from ..schemas import ComplianceStatus
except ImportError:
    from schemas import ComplianceStatus


class RuleValidator:
    """
    Applies objective, non-fuzzy procurement rules:
    - Minimum turnover thresholds
    - Debarment / blacklist status
    - Valid registration dates / active expiry
    """

    @staticmethod
    def validate_turnover(required_amount_lakhs: float, presented_amount_lakhs: float) -> Tuple[ComplianceStatus, str]:
        if presented_amount_lakhs >= required_amount_lakhs:
            return ComplianceStatus.PASS, f"Turnover of ₹{presented_amount_lakhs:.2f}L meets or exceeds requirement of ₹{required_amount_lakhs:.2f}L."
        return ComplianceStatus.FAIL, f"Turnover of ₹{presented_amount_lakhs:.2f}L is below the mandatory threshold of ₹{required_amount_lakhs:.2f}L."

    @staticmethod
    def validate_debarment(is_debarred: bool, debarment_reason: Optional[str] = None) -> Tuple[ComplianceStatus, str]:
        if is_debarred:
            return ComplianceStatus.FAIL, f"Bidder is actively debarred/blacklisted: {debarment_reason or 'Order in force'}."
        return ComplianceStatus.PASS, "No active debarment or blacklist orders found."

    @staticmethod
    def validate_identifier_format(identifier_type: str, identifier_value: str) -> Tuple[ComplianceStatus, str]:
        patterns = {
            "PAN": r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$",
            "GSTIN": r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$",
            "UDYAM": r"^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$"
        }
        pattern = patterns.get(identifier_type.upper())
        if not pattern:
            return ComplianceStatus.REVIEW, f"Unknown statutory identifier scheme: {identifier_type}"

        if re.match(pattern, identifier_value.strip()):
            return ComplianceStatus.PASS, f"{identifier_type} format is valid."
        return ComplianceStatus.FAIL, f"Malformed {identifier_type}: '{identifier_value}' does not match official format."
