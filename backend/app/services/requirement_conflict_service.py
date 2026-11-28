import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tender import (
    TenderDocument,
    TenderRequirement,
    TenderRequirementConflict,
)

AMENDMENT_KEYWORDS = (
    "corrigendum",
    "amended",
    "amendment",
    "revised",
    "substituted",
    "instead of",
    "read as",
    "extended to",
    "modified to",
    "supersedes",
)

SCOPE_PATTERN = re.compile(
    r"\b(lot\s*\d+|package\s*\d+|zone\s*[a-z0-9]+|phase\s*\d+|"
    r"mse|non-mse|msme|startup|general\s+bidder|class-i|class-ii)\b",
    re.IGNORECASE,
)


def _extract_scope_tokens(req: TenderRequirement, doc: Optional[TenderDocument]) -> Set[str]:
    text_blob = " ".join(
        filter(
            None,
            [
                req.normalized_statement,
                req.conditions_and_exceptions,
                req.source_text,
                doc.applicability_scope if doc else None,
            ],
        )
    )
    return {m.group(1).lower().replace("  ", " ") for m in SCOPE_PATTERN.finditer(text_blob)}


def _normalize_numeric_value(
    numeric_value: Optional[str],
    unit: Optional[str],
    currency: Optional[str],
) -> Optional[Tuple[float, str]]:
    """Normalize numeric thresholds with units/currency into comparable (value, dimension)."""
    if not numeric_value:
        return None
    cleaned = re.sub(r"[,\s]", "", str(numeric_value))
    m = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not m:
        return None
    val = float(m.group(0))
    unit_low = (unit or "").lower()
    curr_low = (currency or "").lower()

    # Currency / monetary multipliers
    if "crore" in unit_low or "cr" == unit_low.strip():
        return val * 10_000_000.0, curr_low or "money"
    if "lakh" in unit_low or "lac" in unit_low:
        return val * 100_000.0, curr_low or "money"
    if curr_low in ("inr", "rs", "rs.", "usd", "eur") or "inr" in unit_low:
        return val, curr_low or "money"

    # Time duration normalization (days)
    if "year" in unit_low or "yr" in unit_low:
        return val * 365.0, "days"
    if "month" in unit_low:
        return val * 30.0, "days"
    if "week" in unit_low:
        return val * 7.0, "days"
    if "day" in unit_low:
        return val, "days"

    # Storage normalization (GB)
    if "tb" in unit_low:
        return val * 1024.0, "gb"
    if "gb" in unit_low:
        return val, "gb"

    if "%" in unit_low or "percent" in unit_low:
        return val, "percent"

    return val, unit_low or "scalar"


def _has_amendment_cue(req: TenderRequirement, doc: Optional[TenderDocument]) -> bool:
    if doc and doc.document_role == "CORRIGENDUM":
        return True
    blob = f"{req.source_text} {req.normalized_statement}".lower()
    return any(kw in blob for kw in AMENDMENT_KEYWORDS)


def _map_conflict_type(req_a: TenderRequirement, req_b: TenderRequirement, same_dim: str) -> str:
    if same_dim == "days" and req_a.primary_category == "DATE":
        return "DATE_MISMATCH"
    cat = req_a.primary_category
    if cat == "DEL":
        return "DELIVERY_MISMATCH"
    if cat == "FIN":
        return "FINANCIAL_MISMATCH"
    if cat == "TECH":
        return "TECHNICAL_MISMATCH"
    if cat in ("ELIG", "EXP"):
        return "ELIGIBILITY_MISMATCH"
    if cat in ("DOC", "SUB"):
        return "DOCUMENT_MISMATCH"
    if cat == "DATE":
        return "DATE_MISMATCH"
    return "NUMERIC_MISMATCH"


class TenderRequirementConflictService:
    """Scope-aware cross-document conflict and potential-amendment detector."""

    async def detect_conflicts(self, db: AsyncSession, tender_id: UUID) -> List[TenderRequirementConflict]:
        reqs = (
            await db.execute(
                select(TenderRequirement)
                .where(TenderRequirement.tender_id == tender_id)
                .order_by(TenderRequirement.created_at.asc())
            )
        ).scalars().all()
        if len(reqs) < 2:
            return []

        docs = (
            await db.execute(select(TenderDocument).where(TenderDocument.tender_id == tender_id))
        ).scalars().all()
        doc_map: Dict[UUID, TenderDocument] = {d.id: d for d in docs}

        existing = (
            await db.execute(
                select(TenderRequirementConflict).where(TenderRequirementConflict.tender_id == tender_id)
            )
        ).scalars().all()
        existing_pairs: Dict[Tuple[UUID, UUID], TenderRequirementConflict] = {}
        for ex in existing:
            pair = (min(ex.requirement_a_id, ex.requirement_b_id), max(ex.requirement_a_id, ex.requirement_b_id))
            existing_pairs[pair] = ex

        # Partition by (primary_category, requirement_type) to avoid unbounded O(N^2) all-pairs
        buckets: Dict[Tuple[str, str], List[TenderRequirement]] = defaultdict(list)
        for r in reqs:
            buckets[(r.primary_category, r.requirement_type)].append(r)

        created_or_updated: List[TenderRequirementConflict] = []

        for (_cat, _rtype), items in buckets.items():
            if len(items) < 2:
                continue
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    ra, rb = items[i], items[j]
                    # Skip exact duplicate statements from same document & page
                    if (
                        ra.source_document_id == rb.source_document_id
                        and ra.source_page_number == rb.source_page_number
                        and ra.normalized_statement.strip().lower() == rb.normalized_statement.strip().lower()
                    ):
                        continue

                    doc_a = doc_map.get(ra.source_document_id)
                    doc_b = doc_map.get(rb.source_document_id)

                    # Scope check: explicitly disjoint scopes (e.g. Lot 1 vs Lot 2, MSE vs General) are not conflicts
                    scope_a = _extract_scope_tokens(ra, doc_a)
                    scope_b = _extract_scope_tokens(rb, doc_b)
                    if scope_a and scope_b and scope_a.isdisjoint(scope_b):
                        continue

                    # Period check: different financial periods (e.g. FY2024 vs 3 years) if explicit and disjoint
                    p_a = (ra.period_or_validity or "").strip().lower()
                    p_b = (rb.period_or_validity or "").strip().lower()

                    norm_a = _normalize_numeric_value(ra.numeric_value, ra.unit, ra.currency)
                    norm_b = _normalize_numeric_value(rb.numeric_value, rb.unit, rb.currency)

                    is_amendment = _has_amendment_cue(ra, doc_a) or _has_amendment_cue(rb, doc_b)
                    conflict_found = False
                    conflict_type = "OTHER"
                    severity = "MEDIUM"
                    explanation = ""

                    if norm_a and norm_b and norm_a[1] == norm_b[1]:
                        if abs(norm_a[0] - norm_b[0]) > 1e-6:
                            conflict_found = True
                            conflict_type = _map_conflict_type(ra, rb, norm_a[1])
                            ratio = max(norm_a[0], norm_b[0]) / max(min(norm_a[0], norm_b[0]), 1.0)
                            severity = "HIGH" if (ra.mandatory_status == "MANDATORY" and rb.mandatory_status == "MANDATORY" and ratio >= 1.5) else "MEDIUM"
                            explanation = (
                                f"Normalized values differ ({ra.numeric_value} {ra.unit or ''} {ra.currency or ''} vs "
                                f"{rb.numeric_value} {rb.unit or ''} {rb.currency or ''}) between "
                                f"'{doc_a.original_filename if doc_a else ra.source_document_id}' p.{ra.source_page_number} and "
                                f"'{doc_b.original_filename if doc_b else rb.source_document_id}' p.{rb.source_page_number}."
                            ).strip()
                    elif is_amendment and ra.source_document_id != rb.source_document_id:
                        conflict_found = True
                        conflict_type = _map_conflict_type(ra, rb, "scalar")
                        severity = "MEDIUM"
                        explanation = (
                            f"Potential corrigendum/amendment relationship detected between "
                            f"'{doc_a.original_filename if doc_a else ra.source_document_id}' p.{ra.source_page_number} and "
                            f"'{doc_b.original_filename if doc_b else rb.source_document_id}' p.{rb.source_page_number}."
                        )
                    elif ra.mandatory_status != rb.mandatory_status and "UNCLEAR" not in (ra.mandatory_status, rb.mandatory_status):
                        if ra.source_document_id != rb.source_document_id:
                            conflict_found = True
                            conflict_type = "OTHER"
                            severity = "LOW"
                            explanation = (
                                f"Obligation status differs ({ra.mandatory_status} vs {rb.mandatory_status}) "
                                f"for related {ra.primary_category} requirements across documents."
                            )

                    if not conflict_found:
                        continue

                    pair_key = (min(ra.id, rb.id), max(ra.id, rb.id))
                    rel_type = "POTENTIAL_AMENDMENT" if is_amendment else "CONFLICT"
                    status_val = "NEEDS_REVIEW" if (is_amendment or bool(p_a and p_b and p_a != p_b)) else "DETECTED"
                    scope_summary = ", ".join(sorted(scope_a | scope_b))[:255] if (scope_a or scope_b) else None

                    existing_row = existing_pairs.get(pair_key)
                    if existing_row:
                        # Preserve human-reviewed statuses unless underlying requirement text/values changed
                        conflict_material_changed = (
                            existing_row.explanation != explanation
                            or existing_row.conflict_type != conflict_type
                        )
                        if existing_row.status in ("CONFIRMED", "DISMISSED", "RESOLVED") and not conflict_material_changed:
                            created_or_updated.append(existing_row)
                            continue
                        if existing_row.status in ("CONFIRMED", "DISMISSED", "RESOLVED") and conflict_material_changed:
                            from app.services.review_service import TenderReviewService

                            await TenderReviewService.invalidate_for_source_change(
                                db=db,
                                tender_id=tender_id,
                                requirement_ids=[ra.id, rb.id],
                                previous_sha256=ra.source_document_sha256,
                                current_sha256=rb.source_document_sha256,
                                reason="Underlying requirement changed; conflict assessment requires renewed human review.",
                            )
                            existing_row.conflict_type = conflict_type
                            existing_row.relationship_type = rel_type
                            existing_row.severity = severity
                            existing_row.scope_summary = scope_summary
                            existing_row.explanation = explanation
                            created_or_updated.append(existing_row)
                            continue
                        existing_row.conflict_type = conflict_type
                        existing_row.relationship_type = rel_type
                        existing_row.severity = severity
                        existing_row.status = status_val
                        existing_row.scope_summary = scope_summary
                        existing_row.explanation = explanation
                        created_or_updated.append(existing_row)
                    else:
                        rec = TenderRequirementConflict(
                            tender_id=tender_id,
                            requirement_a_id=pair_key[0],
                            requirement_b_id=pair_key[1],
                            conflict_type=conflict_type,
                            relationship_type=rel_type,
                            severity=severity,
                            status=status_val,
                            scope_summary=scope_summary,
                            explanation=explanation,
                        )
                        db.add(rec)
                        existing_pairs[pair_key] = rec
                        created_or_updated.append(rec)

        await db.flush()
        return created_or_updated
