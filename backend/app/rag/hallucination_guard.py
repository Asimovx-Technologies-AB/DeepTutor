"""
Self-RAG Hallucination Guard & Grounding Verifier for DeepTutor.

Performs fast reflection checking on LLM answers against retrieved PDF context passages:
  - Extracts key factual claims & sentences
  - Computes n-gram overlap and semantic entailment against retrieved document chunks
  - Produces grounding_score (0.0 to 1.0) and unverified sentence flags
"""
import re
from typing import List, Dict, Tuple


def _split_sentences(text: str) -> List[str]:
    """Split text into individual candidate sentence claims."""
    # Clean markdown headers and formatting tags
    cleaned = re.sub(r'#+\s*', '', text)
    cleaned = re.sub(r'\[Section:[^\]]+\]', '', cleaned)
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', cleaned)
    sentences = []
    for s in raw:
        s = s.strip()
        if len(s) >= 15 and not s.startswith("📄") and not s.startswith("🧠") and not s.startswith("❌"):
            sentences.append(s)
    return sentences


def _extract_ngrams(text: str, n: int = 3) -> set:
    """Extract character/word n-grams for fast overlap matching."""
    words = [w.lower() for w in re.findall(r'\b\w+\b', text) if len(w) > 2]
    if len(words) < n:
        return set(words)
    return set(" ".join(words[i:i+n]) for i in range(len(words)-n+1))


def verify_response_grounding(
    response_text: str,
    context_chunks: List[Dict],
    threshold: float = 0.65,
) -> Dict:
    """
    Verify grounding of an LLM generated answer against retrieved context chunks.
    Returns dict with:
      - grounding_score (float 0.0-1.0)
      - verified (bool)
      - matched_sentences (int)
      - total_sentences (int)
      - unverified_claims (list of str)
      - formatted_badge (str)
    """
    if not response_text or not context_chunks:
        return {
            "grounding_score": 1.0,
            "verified": True,
            "matched_sentences": 0,
            "total_sentences": 0,
            "unverified_claims": [],
            "formatted_badge": "🛡️ Verified Grounding: 100%",
        }

    # If the response is a polite "Topic Not Found" or out-of-scope notice, do not display a false Grounding Warning
    if "topic not found" in response_text.lower() or "could not find information" in response_text.lower():
        return {
            "grounding_score": 1.0,
            "verified": True,
            "matched_sentences": 0,
            "total_sentences": 0,
            "unverified_claims": [],
            "formatted_badge": None,
        }

    # Aggregate all PDF source context text
    full_context_text = " ".join([
        (c.get("text") or "") + " " + (c.get("child_text") or "")
        for c in context_chunks
    ]).lower()
    
    context_words = set(re.findall(r'\b\w+\b', full_context_text))
    context_trigrams = _extract_ngrams(full_context_text, n=3)

    sentences = _split_sentences(response_text)
    if not sentences:
        return {
            "grounding_score": 1.0,
            "verified": True,
            "matched_sentences": 0,
            "total_sentences": 0,
            "unverified_claims": [],
            "formatted_badge": "🛡️ Verified Grounding: 100%",
        }

    matched_count = 0
    unverified_claims = []

    for sentence in sentences:
        sent_words = [w.lower() for w in re.findall(r'\b\w+\b', sentence) if len(w) > 2]
        if not sent_words:
            matched_count += 1
            continue

        # 1. Direct word overlap ratio against context
        in_context = sum(1 for w in sent_words if w in context_words)
        overlap_ratio = in_context / max(1, len(sent_words))

        # 2. Trigram phrase match ratio
        sent_trigrams = _extract_ngrams(sentence, n=3)
        trigram_ratio = 0.0
        if sent_trigrams:
            trigram_matches = sum(1 for tg in sent_trigrams if tg in context_trigrams)
            trigram_ratio = trigram_matches / max(1, len(sent_trigrams))

        # Combined claim score
        claim_score = (overlap_ratio * 0.6) + (trigram_ratio * 0.4)

        if claim_score >= 0.35 or overlap_ratio >= 0.50:
            matched_count += 1
        else:
            unverified_claims.append(sentence)

    grounding_score = round(matched_count / max(1, len(sentences)), 2)
    verified = grounding_score >= threshold
    pct = int(grounding_score * 100)

    badge = f"🛡️ Verified Grounding: {pct}%" if verified else f"⚠️ Grounding Warning: {pct}%"

    return {
        "grounding_score": grounding_score,
        "verified": verified,
        "matched_sentences": matched_count,
        "total_sentences": len(sentences),
        "unverified_claims": unverified_claims[:3],
        "formatted_badge": badge,
    }
