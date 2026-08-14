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
