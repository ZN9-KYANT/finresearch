"""Tests for finresearch formatting."""

from finresearch.formatting import fmt_date, fmt_num, fmt_pct, print_table


def test_fmt_num_usd():
    assert fmt_num(1_000_000_000) == "$1.00B"
    assert fmt_num(500_000_000) == "$500.0M"
    assert fmt_num(1_500) == "$1,500"
    assert fmt_num(0.1234) == "$0.1234"


def test_fmt_num_shares():
    assert fmt_num(1_500_000_000, "shares") == "1.50B"
    assert fmt_num(25_000_000, "shares") == "25.0M"
    assert fmt_num(1500, "shares") == "1,500"


def test_fmt_num_nan():
    assert fmt_num(None) == "N/A"
    assert fmt_num(float("nan")) == "N/A"


def test_fmt_pct():
    assert fmt_pct(0.115) == "11.5%"
    assert fmt_pct(25.3, percent_units=True) == "25.3%"
    assert fmt_pct(None) == "N/A"


def test_fmt_pct_units_are_explicit():
    # fractions >= 1 are real ratios (AAPL ROE ~1.49 = 149%), not percent points
    assert fmt_pct(1.49) == "149.0%"
    # percent points under 1 stay as-is (a 0.42% day move is not 42%)
    assert fmt_pct(0.42, percent_units=True) == "0.4%"
    assert fmt_pct(-0.8, percent_units=True) == "-0.8%"


def test_print_table_empty_prints_title_once(capsys):
    print_table(["a"], [], title="T")
    out = capsys.readouterr().out
    assert out.count("## T") == 1
    assert "No data available" in out


def test_fmt_date():
    assert fmt_date("2026-03-31") == "2026-03-31"
    assert fmt_date(None) == "N/A"
