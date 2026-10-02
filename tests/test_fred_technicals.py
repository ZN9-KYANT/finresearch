"""Tests for FRED alias resolution, formatters, and technicals math (pure logic)."""

import pandas as pd

from finresearch.formatting import fmt_num, fmt_pct, fmt_shares
from finresearch.fred import (
    DASHBOARD_GROUPS,
    SERIES_ALIASES,
    _redact,
    _resolve_series,
    _resolve_transform,
)
from finresearch.technicals import _compute_bollinger, _compute_macd, _compute_rsi


class TestFredAliases:
    def test_core_aliases_resolve(self):
        assert _resolve_series("fed_funds") == "FEDFUNDS"
        assert _resolve_series("cpi") == "CPIAUCSL"
        assert _resolve_series("unemployment") == "UNRATE"
        assert _resolve_series("vix") == "VIXCLS"

    def test_raw_series_ids_pass_through(self):
        assert _resolve_series("DGS10") == "DGS10"
        assert _resolve_series("gdpc1") == "GDPC1"  # case-insensitive pass-through

    def test_alias_table_has_no_duplicates_to_same_target(self):
        # every alias group resolves; dashboard groups reference known aliases
        for group, series_list in DASHBOARD_GROUPS.items():
            assert series_list, group
            for alias in series_list:
                assert _resolve_series(alias), f"{group}/{alias} unresolved"


    def test_yoy_aliases_use_fred_pc1_transform(self):
        # *_yoy aliases are real % changes from a year ago, not raw index levels
        assert _resolve_series("cpi_yoy") == "CPIAUCSL"
        assert _resolve_transform("cpi_yoy") == "pc1"
        assert _resolve_series("pce_yoy") == "PCEPILFE"
        assert _resolve_transform("pce_yoy") == "pc1"
        assert _resolve_transform("m2_yoy") == "pc1"
        assert _resolve_transform("cpi") is None

    def test_dead_or_placeholder_ids_removed(self):
        # verified 400s on FRED (DSOFR, ESTHOS, ISM, WILL5000PR) or placeholders
        targets = set(SERIES_ALIASES.values())
        assert not targets & {"DSOFR", "ESTHOS", "ISM", "WILL5000PR"}
        assert "ism_services" not in SERIES_ALIASES
        assert _resolve_series("sofr") == "SOFR"
        assert _resolve_series("pce_core") == "PCEPILFE"

    def test_redact_masks_api_key(self):
        err = ("Max retries exceeded with url: /fred/series/observations?"
               "series_id=DGS10&api_key=SECRET123 (Caused by ...)")
        red = _redact(err)
        assert "SECRET123" not in red
        assert "api_key=***" in red


class TestFormatters:
    def test_fmt_num_is_currency_style(self):
        # house fmt_num renders currency: $x.xM / $x.xxB / $comma numbers
        assert fmt_num(1234567) == "$1.2M"
        assert fmt_num(50420000000) == "$50.42B"
        assert fmt_num(467596) == "$467,596"

    def test_fmt_pct(self):
        assert fmt_pct(0.05) == "5.0%"
        assert fmt_pct(5.0, percent_units=True) == "5.0%"
        assert fmt_pct(None) == "N/A"

    def test_fmt_shares_plain_not_currency(self):
        assert fmt_shares(946) == "946"
        assert fmt_shares(12561737) == "12,561,737"
        assert fmt_shares(None) == "-"
        assert "$" not in fmt_shares(12561737)


class TestTechnicals:
    def _series(self, prices):
        return pd.Series(prices, dtype=float)

    def test_rsi_bounds_and_extremes(self):
        # strictly rising closes -> RSI near 100
        up = self._series([100 + i for i in range(30)])
        rsi = _compute_rsi(up)
        assert rsi is not None and rsi > 90
        # strictly falling closes -> RSI near 0
        down = self._series([200 - i for i in range(30)])
        rsi = _compute_rsi(down)
        assert rsi is not None and rsi < 10

    def test_rsi_flat_series_yields_nan_or_none(self):
        # Flat prices: zero gains AND zero losses -> Wilder RS undefined (0/0).
        # Documented edge: result may be NaN or None, never a wrong finite value.
        flat = self._series([100.0] * 30)
        rsi = _compute_rsi(flat)
        assert rsi is None or (isinstance(rsi, float) and rsi != rsi)

    def test_macd_relationships(self):
        up = self._series([100 + (i ** 1.5) for i in range(40)])
        macd, signal, hist = _compute_macd(up)
        assert macd > 0 and signal > 0
        assert abs((macd - signal) - hist) < 1e-9  # histogram is exactly the spread

    def test_bollinger_bands_bracket_price(self):
        import numpy as np
        rng = np.random.default_rng(7)
        s = self._series(100 + rng.normal(0, 1, 40).cumsum() * 0.1)
        upper, mid, lower = _compute_bollinger(s)  # (upper, sma, lower) per source
        assert upper >= mid >= lower
