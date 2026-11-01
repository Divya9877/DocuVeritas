
import numpy as np
from sentence_transformers import CrossEncoder

MODEL_NAME = "cross-encoder/nli-deberta-v3-small"

# Load the model only when the first comparison is requested.
_model = None

# Output order for this model:
# contradiction, entailment, neutral
LABELS = ["contradiction", "entailment", "neutral"]


def get_model():
    global _model

    if _model is None:
        print("Loading the NLI model for the first time...")
        _model = CrossEncoder(MODEL_NAME)

    return _model


def convert_to_probabilities(scores):
    """
    Convert model logits into valid probabilities.

    If the model already returns valid probabilities, preserve them.
    Otherwise, apply numerically stable softmax.
    """
    scores = np.asarray(scores, dtype=np.float64).reshape(-1)

    if len(scores) != len(LABELS):
        raise ValueError(
            f"Expected {len(LABELS)} model scores, "
            f"but received {len(scores)}."
        )

    if not np.all(np.isfinite(scores)):
        raise ValueError("The model returned non-finite scores.")

    # Avoid converting an already valid probability vector again.
    if (
        np.all(scores >= 0)
        and np.all(scores <= 1)
        and np.isclose(scores.sum(), 1.0, atol=1e-5)
    ):
        return scores

    # Numerically stable softmax for raw logits.
    shifted = scores - np.max(scores)
    exponentials = np.exp(shifted)
    probabilities = exponentials / exponentials.sum()

    return probabilities


def compare_claims(claim_a, claim_b):
    """
    Compare two claims using Natural Language Inference (NLI).

    Returns:
        prediction: contradiction, entailment, or neutral
        scores: probabilities between 0 and 1

    These scores represent model confidence, not a guarantee
    that the real-world documents contradict each other.
    """
    if not isinstance(claim_a, str) or not claim_a.strip():
        raise ValueError("Claim A must be a non-empty string.")

    if not isinstance(claim_b, str) or not claim_b.strip():
        raise ValueError("Claim B must be a non-empty string.")

    model = get_model()

    raw_scores = model.predict([(claim_a, claim_b)])[0]
    probabilities = convert_to_probabilities(raw_scores)

    predicted_index = int(np.argmax(probabilities))

    return {
        "claim_a": claim_a,
        "claim_b": claim_b,
        "prediction": LABELS[predicted_index],
        "scores": {
            LABELS[i]: round(float(probabilities[i]), 6)
            for i in range(len(LABELS))
        }
    }
