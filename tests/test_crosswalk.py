from civicpilot.crosswalk import AgencyCrosswalk, AgencyMapping, load_default_crosswalk


def make_epa_only():
    return AgencyCrosswalk([
        AgencyMapping("Environmental Protection Agency", "environmental-protection-agency", "068"),
    ])


def test_exact_match_is_verified():
    cw = make_epa_only()
    res = cw.resolve("Environmental Protection Agency")
    assert res.verified is True
    assert res.fr_slug == "environmental-protection-agency"
    assert res.usaspending_toptier_code == "068"


def test_exact_match_is_case_insensitive():
    cw = make_epa_only()
    res = cw.resolve("environmental protection agency")
    assert res.verified is True


def test_fuzzy_match_is_flagged_unverified():
    cw = make_epa_only()
    res = cw.resolve("Enviromental Protection Agncy")
    assert res.verified is False
    assert res.fr_slug == "environmental-protection-agency"


def test_no_match_returns_unresolved():
    cw = make_epa_only()
    res = cw.resolve("Ministry of Silly Walks")
    assert res.verified is False
    assert res.fr_slug is None
    assert res.usaspending_toptier_code is None


def test_load_default_crosswalk_resolves_epa():
    cw = load_default_crosswalk()
    res = cw.resolve("Environmental Protection Agency")
    assert res.verified is True
    assert res.usaspending_toptier_code == "068"
