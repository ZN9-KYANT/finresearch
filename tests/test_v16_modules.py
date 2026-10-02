"""Tests for the v1.6 modules: FTD parsing, FINRA parser, 8-K items, currency fmt."""

import io
import zipfile

from finresearch.events8k import _meaning, extract_items
from finresearch.formatting import fmt_num, fmt_pct
from finresearch.ftd import FIELDS, aggregate_top, parse_ftd_zip
from finresearch.short_interest import _normalize, _parse_line, rank


class TestFmtCurrency:
    def test_jpy_with_trillion_tier(self):
        assert fmt_num(34_637_363_544_064, "JPY") == "¥34.64T"
        assert fmt_num(2925.0, "JPY") == "¥2,925"

    def test_usd_unchanged(self):
        assert fmt_num(46_759_600) == "$46.8M"
        assert fmt_num(50_420_000_000) == "$50.42B"

    def test_per_share_currency(self):
        assert fmt_num(351.28, "JPY/shares") == "¥351.28"
        assert fmt_num(4.2, "USD/shares") == "$4.20"

    def test_shares_still_plain(self):
        assert fmt_num(4_349_891, "shares") == "4.3M"

    def test_dividend_yield_percent_units(self):
        assert fmt_pct(3.42, percent_units=True) == "3.4%"
        assert fmt_pct(0.05) == "5.0%"  # legacy fraction path untouched


class TestFTDParsing:
    def _zip_with(self, lines):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("cnsfails208809a.txt", "\n".join(lines))
        return buf.getvalue()

    LINES = [
        "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE",
        "20880901|B6S7WD106|NYXH|2508|NYXOAH S A SHS (BMU)|1.56",
        "20880901|D1668R123|MBGAF|941|MERCEDES BENZ GROUP AG COMMON|54.72",
        "20880914|ZZTEST01|GME|5200000|GAMESTOP CORP|23.45",
        "20880914|NOPE99123|NOPE|3100|NO PRICE NAME|.",
        "Trailer record count 4",
    ]

    def test_parse_zips_pipe_format(self):
        rows, trailer = parse_ftd_zip(self._zip_with(self.LINES))
        assert trailer["record_count"] == "4"
        assert len(rows) == 4
        assert FIELDS[0] == "settlement_date"
        r0 = rows[0]
        assert r0["settlement_date"] == "2088-09-01"
        assert r0["cusip"] == "B6S7WD106"
        assert r0["quantity_fails"] == 2508
        assert r0["price"] == 1.56

    def test_dot_price_means_none(self):
        rows, _ = parse_ftd_zip(self._zip_with(self.LINES))
        nope = [r for r in rows if r["symbol"] == "NOPE"][0]
        assert nope["price"] is None

    def test_aggregate_top_by_value(self):
        rows, _ = parse_ftd_zip(self._zip_with(self.LINES))
        top = aggregate_top(rows, top=2, by="value")
        assert top[0]["symbol"] == "GME"  # 5.2M x 23.45 >> others
        assert top[0]["peak_value_usd"] == 5_200_000 * 23.45

    def test_aggregate_prefers_largest_of_repeats(self):
        lines = self.LINES + ["20880901|ZZTEST01|GME|100|GAMESTOP CORP|23.45"]
        rows, _ = parse_ftd_zip(self._zip_with(lines))
        top = aggregate_top(rows, top=3, by="value")
        gme = [t for t in top if t["symbol"] == "GME"][0]
        assert gme["peak_quantity"] == 5_200_000  # keep the max, not the sum


class TestFinraParse:
    ROW = ("20800415,A,Agilent Technologies Inc.,A,NYSE,4851353,4767556,,2012318,"
           "2.41,,1.76,83797,2080-04-15")
    ROW_COMMA_NAME = ("20800415,AAALF,Aareal Bank AG, AKTIEN,S,OTC,79128,100172,,0,"
                      "999.99,,-21.01,-21044,2080-04-15")

    def test_simple_row(self):
        row = _parse_line(self.ROW)
        norm = _normalize(row)
        assert norm["symbol"] == "A"
        assert norm["name"] == "Agilent Technologies Inc."
        assert norm["short_interest"] == 4_851_353
        assert norm["days_to_cover"] == 2.41
        assert norm["settlement_date"] == "2080-04-15"

    def test_embedded_comma_name_right_anchored(self):
        row = _parse_line(self.ROW_COMMA_NAME)  # 15 comma-parts
        norm = _normalize(row)
        assert norm["symbol"] == "AAALF"
        assert norm["name"] == "Aareal Bank AG, AKTIEN"  # comma preserved
        assert norm["days_to_cover"] is None  # 999.99 sentinel filtered
        assert norm["short_interest"] == 79_128

    def test_rank_filters_sentinel(self):
        rows = [_normalize(_parse_line(self.ROW)),
                _normalize(_parse_line(self.ROW_COMMA_NAME))]
        top = rank(rows, top=2, by="dtc")
        assert len(top) == 1 and top[0]["symbol"] == "A"
        top = rank(rows, top=2, by="si")
        assert top[0]["symbol"] == "A"  # 4.85M > 79K


class TestEvents8k:
    BODY = ("Item 2.02 Results of Operations. On the 8th, Item 9.01 Exhibits. "
            "also Item 1.01 agreements and Item 4.02, auditor.")

    def test_extract_items(self):
        assert extract_items(self.BODY) == ["1.01", "2.02", "4.02", "9.01"]

    def test_meanings(self):
        assert _meaning("2.02") == "results of operations (earnings)"
        assert _meaning("4.01") == "auditor change"
        assert _meaning("4.02") == "non-reliance on prior financials"
        assert _meaning("5.02") == "director/officer change"
        assert _meaning("9.01") == "financial statements & exhibits"
        assert _meaning("9.99") == "see filing"
