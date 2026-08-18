import re

CITATION_PATTERN = re.compile(r"\[(?:doc|award):[\w-]+\]")

# Bracket lookalikes seen in live model output despite the system prompt
# requiring ASCII brackets — prompting alone can't guarantee a
# non-deterministic model's formatting, so normalize before matching rather
# than dropping an otherwise-genuine citation as if it were uncited.
_BRACKET_LOOKALIKES = str.maketrans({"【": "[", "】": "]"})

# Structural lead-ins only — phrases that introduce what follows rather than
# assert a fact. A length check alone can't tell "Here's a summary." apart
# from a short *uncited claim* like "No mismatch was detected."; the latter
# must still be dropped like any other uncited factual sentence.
LEAD_IN_PATTERN = re.compile(
    r"^(here'?s|here is|below is|in summary|to summarize|in short|overall)\b",
    re.IGNORECASE,
)


def enforce_citations(answer_text: str) -> tuple[str, list[str]]:
    """Splits the answer into sentences and keeps only those carrying a
    citation marker, plus clarifying questions and structural lead-ins.
    Uncited factual-looking sentences are dropped rather than passed
    through, enforcing the groundedness guardrail at composition time
    rather than relying on prompting alone.
    """
    answer_text = answer_text.translate(_BRACKET_LOOKALIKES)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer_text.strip()) if s]
    kept: list[str] = []
    dropped: list[str] = []
    for sentence in sentences:
        if CITATION_PATTERN.search(sentence):
            kept.append(sentence)
        elif sentence.rstrip().endswith("?"):
            kept.append(sentence)
        elif LEAD_IN_PATTERN.match(sentence.strip()):
            kept.append(sentence)
        else:
            dropped.append(sentence)
    return " ".join(kept), dropped
