
import re
import hashlib


def extract_claims(document):
    """
    Convert extracted document text into individual claims.
    Preserve the source page or paragraph for traceability.
    """
    claims = []

    for source in document.get("content", []):
        text = source.get("text", "")

        # Split text at sentence-ending punctuation.
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())

        for sentence in sentences:
            sentence = sentence.strip()

            if not sentence:
                continue

            # Ignore very short fragments.
            if len(sentence.split()) < 3:
                continue

            # Generate a stable identifier from source and claim text.
            source_location = (
                f"page:{source['page']}"
                if "page" in source
                else f"paragraph:{source.get('paragraph', 0)}"
            )

            raw_id = (
                document.get("filename", "")
                + source_location
                + sentence
            )

            claim_id = hashlib.sha256(
                raw_id.encode("utf-8")
            ).hexdigest()[:12]

            claims.append({
                "claim_id": claim_id,
                "text": sentence,
                "source_document": document.get("filename"),
                "source_location": source_location,
                "scope": detect_scope(sentence),
                "claim_type": detect_claim_type(sentence)
            })

    return claims


def detect_scope(sentence):
    """Identify simple environment scopes using keywords."""
    text = sentence.lower()

    if "production" in text:
        return "production"

    if "staging" in text or "testing" in text:
        return "testing"

    return "general"


def detect_claim_type(sentence):
    """Identify common directive and permission statements."""
    text = sentence.lower()

    if any(word in text for word in [
        "must not", "shall not", "cannot", "prohibited"
    ]):
        return "prohibition"

    if any(word in text for word in [
        "must", "shall", "required", "mandatory"
    ]):
        return "requirement"

    if any(word in text for word in [
        "may", "can", "allowed", "permitted"
    ]):
        return "permission"

    return "statement"
