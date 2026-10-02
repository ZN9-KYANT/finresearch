"""Tests for finresearch scan (market scans): filter spec + unit contract."""

import pytest

from finresearch import market_scan as ms
from finresearch.market_scan import (
    FIELD_MAP,
    _resolve_sector_or_industry,
    filter_specs,
)


class _Args:
    def __init__(self, **kw):
        defaults = {
            "region": "us", "sector": None, "industry": None,
            "sort": "mktcap", "limit": 20, "ascending": False,
            "within_high": None, "below_high": None, "off_low": None,
        }
        defaults.update(kw)
        self.__dict__.update(defaults)


class TestFilterSpecs:
    def test_range_field_between(self):
        args = _Args(price=[5.0, 100.0])
        assert filter_specs(args) == [("intradayprice", "btwn", [5.0, 100.0])]

    def test_min_only_percent_units(self):
        args = _Args(netmargin_min=20.0)
        assert filter_specs(args) == [
            ("netincomemargin.lasttwelvemonths", "gt", 20.0)]

    def test_min_and_max_raw(self):
        args = _Args(dtc_min=3.0, dtc_max=10.0)
        assert filter_specs(args) == [
            ("days_to_cover_short.value", "gt", 3.0),
            ("days_to_cover_short.value", "lt", 10.0),
        ]

    def test_all_percent_fields_take_percent_numbers(self):
        # the verified unit contract: ratio fields are percent-coded
        assert FIELD_MAP["netmargin"][1] == "percent"
        assert FIELD_MAP["divyield"][1] == "percent"
        assert FIELD_MAP["shortfloat"][1] == "percent"
        assert FIELD_MAP["perf-52w"][1] == "percent"
        assert FIELD_MAP["beta"][1] == "raw"
        assert FIELD_MAP["pe"][1] == "raw"
        assert FIELD_MAP["price"][0] == "intradayprice"

    def test_new_raw_fields_map_correctly(self):
        assert FIELD_MAP["beta"][0] == "beta"
        assert FIELD_MAP["pb"][0] == "pricebookratio.quarterly"
        assert FIELD_MAP["perf-52w"][0] == "fiftytwowkpercentchange"

    def test_no_filters_empty(self):
        assert filter_specs(_Args()) == []


class TestPostFilter:
    """Client-side 52w-extreme filters (fraction units, positive CLI values)."""

    @staticmethod
    def _qt(hi=None, lo=None, sym="X"):
        return {"symbol": sym, "fiftyTwoWeekHighChangePercent": hi,
                "fiftyTwoWeekLowChangePercent": lo}

    def test_within_high_band(self):
        kept, dropped = ms.post_filter(
            [self._qt(hi=-0.10), self._qt(hi=-0.30), self._qt(hi=None)],
            _Args(within_high=0.25))
        assert len(kept) == 1 and dropped == 2

    def test_below_high_dip_band(self):
        kept, dropped = ms.post_filter(
            [self._qt(hi=-0.25), self._qt(hi=-0.10), self._qt(hi=0.05)],
            _Args(below_high=0.2))
        assert len(kept) == 1 and dropped == 2

    def test_off_low(self):
        kept, dropped = ms.post_filter(
            [self._qt(lo=0.35), self._qt(lo=0.10), self._qt(lo=None)],
            _Args(off_low=0.3))
        assert len(kept) == 1 and dropped == 2

    def test_dip_band_20_50(self):
        # quality-dip band: below-high 0.2 AND within-high 0.5 -> -25%/-45% pass
        rows = [self._qt(hi=-0.25, sym="IN"), self._qt(hi=-0.10, sym="SHALLOW"),
                self._qt(hi=-0.60, sym="DEEP"), self._qt(hi=-0.45, sym="IN2")]
        kept, dropped = ms.post_filter(rows, _Args(below_high=0.2, within_high=0.5))
        assert {q["symbol"] for q in kept} == {"IN", "IN2"}
        assert dropped == 2

    def test_combined_checks_all_must_pass(self):
        rows = [self._qt(hi=-0.25, lo=0.35, sym="BOTH"),
                self._qt(hi=-0.25, lo=0.10, sym="TOO_CLOSE_TO_LOW")]
        kept, _ = ms.post_filter(rows, _Args(below_high=0.2, off_low=0.3))
        assert [q["symbol"] for q in kept] == ["BOTH"]

    def test_no_filters_passthrough(self):
        rows = [self._qt(hi=-0.9)]
        kept, dropped = ms.post_filter(rows, _Args())
        assert kept == rows and dropped == 0

    def test_missing_payload_value_dropped(self):
        kept, dropped = ms.post_filter(
            [{"symbol": "Y"}, self._qt(hi=-0.1)], _Args(within_high=0.25))
        assert len(kept) == 1 and dropped == 1

    def test_template_keys_include_post_filters(self):
        # templates can carry within-high/below-high/off-low
        valid = ms._valid_keys()
        assert {"within-high", "below-high", "off-low"} <= valid


class TestSectorResolution:
    def test_fuzzy_sector_hit(self):
        name, hits = _resolve_sector_or_industry("sector", "financ")
        assert "financial" in str(name).lower()
        assert len(hits) >= 1

    def test_unknown_raises_with_candidates(self):
        with pytest.raises(ValueError, match="vocabulary"):
            _resolve_sector_or_industry("sector", "quantum-bananas")
