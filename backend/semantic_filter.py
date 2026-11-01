
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model = None


def get_model():
    global _model

    if _model is None:
        print("Loading semantic similarity model...")
        _model = SentenceTransformer(MODEL_NAME)

    return _model


def find_candidate_pairs(claims_a, claims_b, threshold=0.35, top_k=3):
    """
    Return semantically related claim pairs.

    Each claim must contain a 'text' field.
    Similarity scores are ranking signals, not probabilities
    of contradiction.
    """
    if not claims_a or not claims_b:
        return []

    texts_a = [claim["text"] for claim in claims_a]
    texts_b = [claim["text"] for claim in claims_b]

    model = get_model()

    embeddings_a = model.encode(
        texts_a, convert_to_tensor=True, normalize_embeddings=True
    )
    embeddings_b = model.encode(
        texts_b, convert_to_tensor=True, normalize_embeddings=True
    )

    similarities = cos_sim(embeddings_a, embeddings_b)

    # Keep the strongest matches for each claim in both documents.
    selected = set()

    for i in range(len(claims_a)):
        k = min(top_k, len(claims_b))
        scores, indices = similarities[i].topk(k)

        for score, j in zip(scores.tolist(), indices.tolist()):
            if score >= threshold:
                selected.add((i, j))

    for j in range(len(claims_b)):
        k = min(top_k, len(claims_a))
        scores, indices = similarities[:, j].topk(k)

        for score, i in zip(scores.tolist(), indices.tolist()):
            if score >= threshold:
                selected.add((i, j))

    return [
        {
            "claim_a": claims_a[i],
            "claim_b": claims_b[j],
            "similarity": round(
                float(similarities[i, j].item()), 4
            )
        }
        for i, j in sorted(selected)
    ]
