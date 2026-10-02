"""Tests for the FOMC hawkish/dovish scorer (pure logic, no network)."""

from finresearch.fomc import DOVISH_TERMS, HAWKISH_TERMS, _analyze_sentiment


def test_strongly_hawkish_text():
    text = ("The Committee is prepared to be aggressive and vigilant, "
            "maintaining a restrictive stance to firmly tighten policy. "
            "Aggressive vigilant restrictive firm tighten.")
    s = _analyze_sentiment(text)
    assert s["hawkish_score"] > s["dovish_score"]
    assert s["hawkish_pct"] >= 65
    assert s["stance"] == "hawkish"


def test_strongly_dovish_text():
    text = ("Policy remains accommodative as the Committee stays patient, "
            "easing pressures and allowing transitory factors to fade. "
            "Accommodative patient easing transitory accommodation.")
    s = _analyze_sentiment(text)
    assert s["dovish_score"] > s["hawkish_score"]
    assert s["dovish_pct"] >= 65
    assert s["stance"] == "dovish"


def test_neutral_text_scores_neutral():
    text = "The Committee will assess the outlook and adjust as appropriate."
    s = _analyze_sentiment(text)
    assert s["stance"] == "neutral"
    assert abs(s["hawkish_pct"] - 50) < 0.01


def test_empty_text_is_neutral():
    s = _analyze_sentiment("")
    assert s["stance"] == "neutral"
    assert s["hawkish_pct"] == 50
    assert s["hawkish_terms"] == {}
    assert s["dovish_terms"] == {}


def test_term_counts_and_scores_are_consistent():
    text = "vigilant vigilant vigilant"
    s = _analyze_sentiment(text)
    assert "vigilant" in s["hawkish_terms"]
    hit = s["hawkish_terms"]["vigilant"]
    assert hit["count"] == 3
    assert hit["score"] == 3 * hit["weight"]
    assert s["hawkish_score"] == hit["score"]


def test_case_insensitive_matching():
    s = _analyze_sentiment("ACCOMMODATIVE accommodative Accommodative")
    assert s["dovish_score"] > 0
    assert s["stance"] == "dovish"


def test_whole_word_matching_ease_is_not_increase():
    # regression: 'ease' (dovish) used to match increase/release/please
    s = _analyze_sentiment("The Committee decided to increase the target range. "
                           "Please see the release.")
    assert "ease" not in s["dovish_terms"]
    assert s["dovish_score"] == 0


def test_longest_phrase_counted_once():
    s = _analyze_sentiment("The Committee is strongly committed to its goal.")
    assert s["hawkish_terms"]["strongly committed"]["count"] == 1
    assert "committed" not in s["hawkish_terms"]


def test_plural_matches():
    s = _analyze_sentiment("further rate cuts")
    assert s["dovish_terms"]["rate cut"]["count"] == 1


def test_no_term_scored_on_both_sides():
    assert not set(HAWKISH_TERMS) & set(DOVISH_TERMS)
