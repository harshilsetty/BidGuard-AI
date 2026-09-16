"""
Extracts factual claims, credentials, and statutory numbers from bidder submissions.
"""

from typing import List
import uuid
import re
from ..schemas import ExtractedEvidence


class EvidenceExtractor:
    """
    Parses bidder submitted documents to find evidence chunks and key entity identifiers.
    """

    PAN_REGEX = r"[A-Z]{5}[0-9]{4}[A-Z]{1}"
    GSTIN_REGEX = r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}"
    UDYAM_REGEX = r"UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}"

    def extract_evidence_chunks(self, pages: List[dict], filename: str) -> List[ExtractedEvidence]:
        evidence_list: List[ExtractedEvidence] = []

        for page in pages:
            text = page.get("text", "")
            page_num = page.get("page", 1)

            # Extract statutory identifiers
            identifiers = []
            for pan in re.findall(self.PAN_REGEX, text):
                identifiers.append(f"PAN:{pan}")
            for gst in re.findall(self.GSTIN_REGEX, text):
                identifiers.append(f"GSTIN:{gst}")
            for udyam in re.findall(self.UDYAM_REGEX, text):
                identifiers.append(f"UDYAM:{udyam}")

            # Chunk paragraphs
            paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
            for para in paragraphs:
                evidence = ExtractedEvidence(
                    evidence_id=f"EVD-{uuid.uuid4().hex[:6].upper()}",
                    source_document=filename,
                    page_number=page_num,
                    extracted_text=para,
                    entity_names=identifiers,
                    dates=[],
                    monetary_values=[]
                )
                evidence_list.append(evidence)

        return evidence_list
