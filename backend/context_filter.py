
from datetime import datetime


def parse_date(value):
    """Parse a date in YYYY-MM-DD format."""
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def analyze_context(claim_a, claim_b):
    """
    Check whether two claims have compatible scopes and versions.

    Each claim may contain:
    text, scope, environment, version, effective_date,
    and superseded_by.
    """
    scope_a = claim_a.get("scope", "general")
    scope_b = claim_b.get("scope", "general")

    env_a = claim_a.get("environment", scope_a)
    env_b = claim_b.get("environment", scope_b)

    # Explicitly different environments should not be compared
    # as if they apply to the same operating conditions.
    if (
        env_a != env_b
        and env_a != "general"
        and env_b != "general"
    ):
        return {
            "decision": "context_variance",
            "compare_with_nli": False,
            "reason": (
                f"Different environments: {env_a} and {env_b}."
            )
        }

    # An explicitly superseded claim is historical.
    if claim_a.get("superseded_by") or claim_b.get("superseded_by"):
        return {
            "decision": "historical",
            "compare_with_nli": False,
            "reason": "At least one claim has been superseded."
        }

    date_a = parse_date(claim_a.get("effective_date"))
    date_b = parse_date(claim_b.get("effective_date"))

    # Invalid dates must be corrected rather than silently ignored.
    for claim in (claim_a, claim_b):
        value = claim.get("effective_date")
        if value and parse_date(value) is None:
            return {
                "decision": "needs_metadata_review",
                "compare_with_nli": False,
                "reason": (
                    f"Invalid effective date: {value}. "
                    "Use YYYY-MM-DD."
                )
            }

    # Different effective dates do not by themselves prove that
    # one policy supersedes another. Keep both for comparison.
    if date_a and date_b and date_a != date_b:
        return {
            "decision": "different_effective_dates",
            "compare_with_nli": True,
            "reason": (
                "Claims have different effective dates; "
                "review their validity periods."
            )
        }

    return {
        "decision": "comparable",
        "compare_with_nli": True,
        "reason": "No blocking context or lifecycle rule was found."
    }
