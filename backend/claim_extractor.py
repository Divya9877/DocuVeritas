
import re
import hashlib


# Metadata patterns that should not be treated as policy claims.
METADATA_PATTERNS = [
    r"^page\s+\d+\s*$",
    r"^abc technologies\s*$",
    r"^employee it usage policy\s*$",
    r"^information security policy\s*$",
    r"^internal policy\s*[•|]\s*version\s+[\w.]+\s*[•|]\s*demo scenario\s*$",
    r"^document control\s*$",
    r"^purpose and scope\s*$",
    r"^important\s*:\s*this is a fictional policy.*$",
]

METADATA_REGEXES = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in METADATA_PATTERNS
]

DEMO_BOILERPLATE = [
    "synthetic demonstration document",
    "fictional policy created for a college project",
    "constructed for a controlled demo",
    "review and approve all real organizational policies",
    "not an approved real-world policy",
    "should not be used operationally",
    "intended for testing document comparison",
]


def is_metadata(text):
    """Return True for known document metadata and demo boilerplate."""
    cleaned = re.sub(r"\s+", " ", text).strip()

    if not cleaned:
        return True

    lower = cleaned.lower()

    # Filter demo labels and disclaimers, including wrapped text.
    if any(phrase in lower for phrase in DEMO_BOILERPLATE):
        return True

    if (
        "internal policy" in lower
        and "version" in lower
        and "demo scenario" in lower
    ):
        return True

    for pattern in METADATA_REGEXES:
        if pattern.fullmatch(cleaned):
            return True

    # Common document-control labels.
    if re.match(
        r"^(document id|policy owner|applies to|review cycle|"
        r"classification|effective date)\s*:",
        cleaned,
        re.IGNORECASE,
    ):
        return True

    return False


def clean_document_text(text):
    """Remove known demo cover text and normalize PDF line wrapping."""
    # Remove the known synthetic demo title.
    text = re.sub(
        r"ABC Technologies\s*\|\s*Synthetic demonstration document",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Remove known policy titles when they occur as standalone headings.
    text = re.sub(
        r"(?m)^\s*(Employee IT Usage Policy|Information Security Policy)\s*$",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Remove version and demo labels.
    text = re.sub(
        r"Internal Policy\s*[•|]\s*Version\s*[\w.]+\s*[•|]\s*Demo scenario",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Remove the synthetic-document disclaimer.
    text = re.sub(
        r"IMPORTANT:\s*This is a fictional policy created for a college project demonstration\.?",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Remove the other known demo disclaimer.
    text = re.sub(
        r"This policy was constructed for a controlled demo;?\s*"
        r"review and approve all real organizational policies "
        r"through the appropriate process\.?",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Remove standalone page-number labels.
    text = re.sub(
        r"(?m)^\s*Page\s+\d+\s*$",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Join lines broken by PDF extraction.
    text = re.sub(r"\s+", " ", text).strip()

    return text


def extract_claims(document):
    """
    Extract sentence-level claims from parsed document content.
    Preserve source locations for traceability.
    """
    claims = []
    seen = set()

    for source in document.get("content", []):
        original_text = source.get("text", "")

        if not isinstance(original_text, str):
            continue

        if not original_text.strip():
            continue

        text = clean_document_text(original_text)

        if not text:
            continue

        # Split text into sentence candidates.
        sentences = re.split(r"(?<=[.!?])\s+", text)

        for sentence in sentences:
            sentence = sentence.strip()

            # Remove leading section numbering, e.g. "2.1 ".
            sentence = re.sub(
                r"^\d+(?:\.\d+)*\.?\s+",
                "",
                sentence,
            ).strip()

            if not sentence or is_metadata(sentence):
                continue

            words = sentence.split()

            # Ignore short fragments.
            if len(words) < 5:
                continue

            # Ignore obvious unfinished list fragments.
            if words[-1].strip(".,;:").lower() in {
                "and", "or", "the", "of", "to", "for",
                "with", "including", "such", "as",
            }:
                continue

            normalized = sentence.casefold()

            # Avoid duplicate claims within the same document.
            if normalized in seen:
                continue

            seen.add(normalized)

            if "page" in source:
                source_location = f"page:{source['page']}"
            else:
                source_location = (
                    f"paragraph:{source.get('paragraph', 0)}"
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
                "claim_type": detect_claim_type(sentence),
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
    """Classify common requirement, prohibition, and permission wording."""
    text = sentence.lower()

    if any(phrase in text for phrase in [
        "must not",
        "shall not",
        "cannot",
        "prohibited",
        "do not need to",
        "does not need to",
        "not required",
        "no requirement to",
    ]):
        return "prohibition"

    if any(word in text for word in [
        "must",
        "shall",
        "required",
        "mandatory",
    ]):
        return "requirement"

    if any(word in text for word in [
        "may",
        "can",
        "allowed",
        "permitted",
    ]):
        return "permission"

    return "statement"
