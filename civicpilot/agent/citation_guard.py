import re

CITATION_PATTERN = re.compile(r"\[(?:doc|award):[\w-]+\]")
SHORT_SENTENCE_THRESHOLD = 40


def enforce_citations(answer_text: str) -> tuple[str, list[str]]:
    """Splits the answer into sentences and keeps only those carrying a
    citation marker, plus clarifying questions and short connective
    lead-ins. Uncited factual-looking sentences are dropped rather than
    passed through, enforcing the groundedness guardrail at composition
    time rather than relying on prompting alone.
    """
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer_text.strip()) if s]
    kept: list[str] = []
    dropped: list[str] = []
    for sentence in sentences:
        if CITATION_PATTERN.search(sentence):
            kept.append(sentence)
        elif sentence.rstrip().endswith("?"):
            kept.append(sentence)
        elif len(sentence) < SHORT_SENTENCE_THRESHOLD:
            kept.append(sentence)
        else:
            dropped.append(sentence)
    return " ".join(kept), dropped
