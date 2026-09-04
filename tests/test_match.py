"""Regression cases from hand-checking the first CDC pass (2026-09-04).

Each case is a real (recipient, BMF candidate) pair that the first matcher got wrong,
plus the correct pairs that the fix must not break.
"""
from grantee_resolver.match import best_match, normalize


def bmf(name, city="X", zip_="00000", ein="1"):
    return {"EIN": ein, "NAME": name, "CITY": city, "ZIP": zip_, "NTEE_CD": "", "REVENUE_AMT": ""}


def test_exact_name_beats_fuzzy_name_with_matching_geo():
    # Research Triangle Institute: BMF says Durham, USAspending says Research Triangle Park.
    cands = [bmf("RESEARCH TRIANGLE INSTITUTE", "DURHAM", "27709", ein="rti"),
             bmf("RESEARCH TRIANGLE INSTITUE POST RETIREMENT HEALTH BENEFITS TRUST", "RTP", "27709", ein="trust")]
    m = best_match("RESEARCH TRIANGLE INSTITUTE", "RESEARCH TRIANGLE PARK", "27709", cands)
    assert (m.tier, m.ein) == ("YES", "rti")


def test_governance_words_are_the_same_org():
    m = best_match("THE LELAND STANFORD JUNIOR UNIVERSITY", "STANFORD", "94305",
                   [bmf("THE BOARD OF TRUSTEES OF THE LELAND STANFORD JUNIOR UNIVERSITY", "STANFORD", "94305")])
    assert (m.tier, m.method) == ("YES", "exact-name+geo-modulo-governance")
    m = best_match("UNIVERSITY OF CALIFORNIA, DAVIS", "DAVIS", "95618",
                   [bmf("REGENTS OF THE UNIVERSITY OF CALIFORNIA AT DAVIS", "DAVIS", "95616")])
    assert m.tier == "YES"


def test_university_foundation_is_vetoed():
    m = best_match("UNIVERSITY OF WASHINGTON", "SEATTLE", "98195",
                   [bmf("UNIVERSITY OF WASHINGTON SCHOOL OF LAW FOUNDATION", "SEATTLE", "98195")])
    assert m.tier == "NO" and m.ein is None and "vetoed: FOUNDATION" in m.method


def test_chapter_alumni_team_are_vetoed():
    for cand in ("GEORGETOWN UNIVERSITY CHAPTER SIGMA XI SCIENTIFIC RESEARCH SOCIETY",
                 "UNIVERSITY OF SOUTH FLORIDA ALUMNI ASSOCIATION INC",
                 "TEXAS EQUESTRIAN TEAM AT THE UNIVERSITY OF TEXAS AT AUSTIN"):
        for grantee in ("GEORGETOWN UNIVERSITY", "UNIVERSITY OF SOUTH FLORIDA", "UNIVERSITY OF TEXAS AT AUSTIN"):
            m = best_match(grantee, "X", "00000", [bmf(cand, "X", "00000")])
            assert m.tier == "NO", (grantee, cand, m)


def test_subset_match_without_affiliate_word_is_at_most_maybe():
    m = best_match("WASHINGTON STATE UNIVERSITY", "PULLMAN", "99164",
                   [bmf("WASHINGTON STATE UNIVERSITY GLOBAL HEALTH", "PULLMAN", "99164")])
    assert (m.tier, m.method) == ("MAYBE", "name-contained")


def test_reverse_subset_is_at_most_maybe():
    # 'CARE & CARE' normalizes to 'CARE CARE', a token subset of 'ALLIANCE CARE 360'.
    m = best_match("ALLIANCE CARE 360", "CHICAGO", "60639", [bmf("CARE & CARE", "CHICAGO", "60639")])
    assert m.tier == "NO"


def test_low_token_overlap_is_no():
    m = best_match("UNIVERSITY OF CALIFORNIA, LOS ANGELES", "LOS ANGELES", "90095",
                   [bmf("UNIVERSITY RELIGIOUS CONFERENCE", "LOS ANGELES", "90024")])
    assert m.tier == "NO"
    m = best_match("INTERNATIONAL ORGANIZATION FOR MIGRATION", "WASHINGTON", "20036",
                   [bmf("INTERNATIONAL ORGANIZATION DEVELOPMENT ASSOCIATION", "WASHINGTON", "20036")])
    assert m.tier == "NO"


def test_health_district_abbreviation_is_gov():
    assert best_match("SOUTHERN NEVADA HEALTH DIST", "LAS VEGAS", "89106", [bmf("SOUTHERN NEVADA AREA SERVICES INC")]).tier == "GOV"


def test_ordinary_suffix_variants_still_exact():
    assert normalize("ALTAMED HEALTH SERVICES CORPORATION") == normalize("ALTAMED HEALTH SERVICES CORP")
    assert normalize("THE JOHNS HOPKINS UNIVERSITY") == normalize("JOHNS HOPKINS UNIVERSITY")
    assert normalize("ASSOCIATION OF ASIAN/PACIFIC COMMUNITY HEALTH ORGANIZATIONS") == normalize("ASSOCIATION OF ASIAN-PACIFIC COMMUNITY HEALTH ORGANIZATIONS")


def test_governance_rule_keeps_word_order_and_prefers_literal_match():
    cands = [bmf("CALIFORNIA UNIVERSITY", "SAN DIEGO", "92101", ein="bogus"),
             bmf("REGENTS OF THE UNIVERSITY OF CALIFORNIA", "OAKLAND", "94607", ein="uc")]
    m = best_match("REGENTS OF THE UNIVERSITY OF CALIFORNIA, THE", "BERKELEY", "94720", cands)
    assert (m.tier, m.ein, m.method) == ("YES", "uc", "exact-name")


def test_affiliate_veto_applies_to_fuzzy_candidates_too():
    m = best_match("University of Texas at Austin", "AUSTIN", "78712", [bmf("UNIVERSITY OF TEXAS FOUNDATION", "AUSTIN", "78701")])
    assert m.tier == "NO" and "vetoed: FOUNDATION" in m.method
    m = best_match("UNIVERSITY OF CALIFORNIA, LOS ANGELES", "LOS ANGELES", "90095",
                   [bmf("UNIVERSITY OF CALIFORNIA LOS ANGELES PANHELLENIC ASSOCIATION", "LOS ANGELES", "90024")])
    assert m.tier == "NO"


def test_no_tier_carries_no_identifiers():
    m = best_match("NEW MEXICO PERINATAL COLLABORATIVE", "SANTA FE", "87508", [bmf("NEW MEXICO ALIVE", "SANTA FE", "87508", ein="x")])
    assert m.tier == "NO" and m.ein is None and m.ntee is None and m.revenue is None
    assert m.bmf_name == "NEW MEXICO ALIVE" and "closest rejected" in m.method
