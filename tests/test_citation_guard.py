from civicpilot.agent.citation_guard import enforce_citations


def test_enforce_citations_keeps_cited_sentences():
    text = "The EPA proposed a new rule [doc:2026-12345] affecting emissions."
    kept, dropped = enforce_citations(text)
    assert "[doc:2026-12345]" in kept
    assert dropped == []


def test_enforce_citations_drops_uncited_factual_claims():
    text = (
        "The EPA proposed a new rule [doc:2026-12345]. "
        "The agency spent one billion dollars on enforcement this year."
    )
    kept, dropped = enforce_citations(text)
    assert "[doc:2026-12345]" in kept
    assert "one billion dollars" not in kept
    assert len(dropped) == 1


def test_enforce_citations_keeps_clarifying_questions():
    text = "Did you mean fiscal year 2026 or calendar year 2026?"
    kept, dropped = enforce_citations(text)
    assert kept == text
    assert dropped == []


def test_enforce_citations_keeps_short_lead_ins():
    text = "Here's a summary. EPA proposed a rule [doc:2026-1]."
    kept, dropped = enforce_citations(text)
    assert "Here's a summary." in kept
    assert "[doc:2026-1]" in kept
    assert dropped == []


def test_enforce_citations_drops_short_uncited_factual_claims():
    """A short factual sentence with no citation must be dropped like any
    other uncited claim — length alone isn't evidence it's a connective
    lead-in rather than a claim. Regression case: 'No mismatch was detected.'
    (26 chars) survived as the entire answer on a live run because it fell
    under the length threshold while the real (longer) uncited claims around
    it were correctly dropped.
    """
    text = (
        "The EPA proposed a new rule [doc:2026-12345]. "
        "No mismatch was detected."
    )
    kept, dropped = enforce_citations(text)
    assert "[doc:2026-12345]" in kept
    assert "No mismatch was detected." not in kept
    assert "No mismatch was detected." in dropped


def test_enforce_citations_recognizes_fullwidth_brackets():
    """Regression case found during Task 16 live verification: the model
    (openai/gpt-oss-120b on Groq) occasionally emits a real, correctly-sourced
    citation using CJK fullwidth brackets (U+3010/U+3011) instead of ASCII
    square brackets, despite the system prompt explicitly requiring ASCII.
    Prompting alone can't guarantee a non-deterministic model's output
    format, so the guard must normalize the common lookalike before matching
    — otherwise a genuinely-cited claim is dropped as if it were uncited,
    which is the opposite of what the citation guardrail is supposed to do.
    """
    text = "The DoD obligated $501B in FY2025【award:097-FY2025】."
    kept, dropped = enforce_citations(text)
    assert "[award:097-FY2025]" in kept
    assert dropped == []
