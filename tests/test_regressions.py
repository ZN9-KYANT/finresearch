"""Regression tests for audit fixes: shared EDGAR plumbing, 8-K items, FTD
parse guards, config, CLI laziness, gappers parser, screener filters, units."""

import io
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from types import SimpleNamespace

import pytest

from finresearch import config, edgar_common, events8k, ftd, premarket_gappers, screener
from finresearch.market_scan import _row_from_quote
from finresearch.yfinance_cmd import _fmt


class TestEdgarCommon:
    XML = "<root><a><b>1</b></a><b>2</b><c><b> 3 </b></c></root>"

    def test_find_all_excludes_root_and_keeps_doc_order(self):
        root = ET.fromstring(self.XML)
        assert [e.text.strip() for e in edgar_common.find_all(root, "b")] == ["1", "2", "3"]
        assert edgar_common.find_all(root, "root") == []

    def test_first_and_child_text(self):
        root = ET.fromstring(self.XML)
        assert edgar_common.first(root, "b").text == "1"
        assert edgar_common.child_text(root, "c", "b") == "3"
        assert edgar_common.child_text(root, "zzz") is None
        assert edgar_common.child_text(None, "b") is None

    def test_bare_primary_doc_trusted_without_directory_fetch(self, monkeypatch):
        def no_network(*a, **k):
            raise AssertionError("index.json must not be fetched")
        monkeypatch.setattr(edgar_common, "filing_index", no_network)
        assert edgar_common.filing_doc_name("1", "0000-00-000001", "d8k.htm") == "d8k.htm"

    def test_viewer_path_resolved_via_directory(self, monkeypatch):
        monkeypatch.setattr(edgar_common, "filing_index",
                            lambda cik, acc: ("index-headers.html", "primary_doc.htm", "x.jpg"))
        assert edgar_common.filing_doc_name("1", "a", "xslX/primary_doc.xml") == "primary_doc.htm"

    def test_list_filings_carries_items_column(self, monkeypatch):
        rec = {"form": ["8-K", "10-Q", "8-K"],
               "filingDate": ["2099-01-03", "2099-01-02", "2099-01-01"],
               "accessionNumber": ["a1", "a2", "a3"],
               "primaryDocument": ["d1.htm", "d2.htm", "d3.htm"],
               "items": ["2.02,9.01", "", "5.02"]}
        monkeypatch.setattr(edgar_common, "submissions", lambda cik: rec)
        rows = edgar_common.list_filings("1", ["8-K"], days=None)
        assert [r["accession"] for r in rows] == ["a1", "a3"]
        assert rows[0]["items"] == "2.02,9.01"


class TestEvents8kItems:
    def test_items_come_from_submissions_not_documents(self, monkeypatch):
        monkeypatch.setattr(events8k, "resolve_cik", lambda t: "0000000001")
        monkeypatch.setattr(events8k, "list_filings", lambda cik, forms, days: [
            {"form": "8-K", "filing_date": "2099-01-01", "accession": "a1",
             "primary_doc": "d.htm", "items": "9.01,2.02"}])

        def no_fetch(*a, **k):
            raise AssertionError("document must not be fetched when items are known")
        monkeypatch.setattr(events8k, "fetch_doc_text", no_fetch)
        rows = events8k.scan_8k(["TEST"], days=30)
        assert rows[0]["items"] == ["2.02", "9.01"]

    def test_empty_items_fall_back_to_document_grep(self, monkeypatch):
        monkeypatch.setattr(events8k, "resolve_cik", lambda t: "0000000001")
        monkeypatch.setattr(events8k, "list_filings", lambda cik, forms, days: [
            {"form": "8-K", "filing_date": "2001-01-01", "accession": "a1",
             "primary_doc": "d.htm", "items": ""}])
        monkeypatch.setattr(events8k, "fetch_doc_text",
                            lambda cik, acc, prefer_primary=None: "Item 4.02 Non-reliance")
        assert events8k.scan_8k(["TEST"])[0]["items"] == ["4.02"]


class TestFtdGuards:
    @staticmethod
    def _zip(lines):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("f.txt", "\n".join(lines))
        return buf.getvalue()

    def test_malformed_row_skipped_and_trailer_mismatch_warned(self, capsys):
        raw = self._zip([
            "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE",
            "20990101|C1|AAA|100|A CORP|1.00",
            "20990101|C2|BBB|not-a-number|B CORP|2.00",
            "Trailer record count 2",
        ])
        rows, trailer = ftd.parse_ftd_zip(raw)
        assert [r["symbol"] for r in rows] == ["AAA"]
        assert "trailer says 2 records, parsed 1" in capsys.readouterr().err

    def test_real_two_line_trailer(self, capsys):
        # live layout: record count, then total quantity (must not overwrite)
        raw = self._zip([
            "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE",
            "20990101|C1|AAA|100|A CORP|1.00",
            "Trailer record count 1",
            "Trailer total quantity of shares 100",
        ])
        rows, trailer = ftd.parse_ftd_zip(raw)
        assert trailer == {"record_count": "1", "total_quantity": "100"}
        assert capsys.readouterr().err == ""

    def test_discovery_probe_is_the_download(self, monkeypatch):
        calls = []

        def fake_get(url, timeout=25):
            calls.append(url)
            if url.endswith("b.zip"):
                raise OSError("404")
            return b"zip-bytes"
        monkeypatch.setattr(ftd, "_get", fake_get)
        ftd._download.cache_clear()
        found = ftd.latest_ftd_files(count=1)
        assert len(found) == 1
        n = len(calls)
        ftd._download(*found[0])  # what fetch_ftd does next: no second download
        assert len(calls) == n
        ftd._download.cache_clear()


class TestConfig:
    def test_watchlist_from_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FINRESEARCH_CONFIG_DIR", str(tmp_path))
        (tmp_path / "watchlist.txt").write_text("# mine\nmsft\n\n  # indented comment\nnvda\n")
        assert config.load_watchlist() == ["MSFT", "NVDA"]

    def test_watchlist_demo_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FINRESEARCH_CONFIG_DIR", str(tmp_path))
        assert config.load_watchlist() == config.DEMO_WATCHLIST

    def test_user_agent_is_versioned_and_overridable(self, monkeypatch):
        from finresearch import __version__
        monkeypatch.delenv("FINRESEARCH_SEC_UA", raising=False)
        assert config.user_agent() == f"finresearch/{__version__} contact@example.com"
        monkeypatch.setenv("FINRESEARCH_SEC_UA", "tool/1.0 me@domain.org")
        assert config.user_agent() == "tool/1.0 me@domain.org"


class TestCli:
    def test_version_flag(self):
        from finresearch import __version__
        out = subprocess.run([sys.executable, "-m", "finresearch.cli", "--version"],
                             capture_output=True, text=True, check=True)
        assert out.stdout.strip() == f"finresearch {__version__}"

    def test_cli_import_does_not_load_pandas(self):
        code = "import sys, finresearch.cli; print('pandas' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, check=True)
        assert out.stdout.strip() == "False"


class TestGappersParser:
    def test_short_rows_skipped_not_crashing(self, monkeypatch):
        cell = "<td>x</td>"
        html = ("<table><tr><th>Pre-mkt gap</th></tr>"
                f"<tr><td><a>ABC</a></td>{cell * 7}</tr>"          # 8 cells: too short
                f"<tr><td><a>XYZ</a></td>{cell * 9}</tr></table>")  # 10 cells: parsed
        resp = SimpleNamespace(text=html, raise_for_status=lambda: None)
        monkeypatch.setattr(premarket_gappers.requests, "get", lambda *a, **k: resp)
        rows = premarket_gappers._fetch_gappers_tradingview()
        assert [r["ticker"] for r in rows] == ["XYZ"]


class TestScreenerFilters:
    ARGS = dict(min_pe=None, max_pe=None, min_fwd_pe=None, max_fwd_pe=None, min_peg=None,
                max_peg=None, min_revgrowth=None, min_margin=None, max_debt_equity=None,
                min_mktcap=None, max_mktcap=None, min_beta=None, max_beta=None,
                sector=None, industry=None)

    def _args(self, **kw):
        return SimpleNamespace(**{**self.ARGS, **kw})

    def test_missing_metric_fails_an_active_filter(self):
        loss_maker = {"ticker": "L", "trailing_pe": None}
        assert not screener._passes_filters(loss_maker, self._args(max_pe=20))

    def test_missing_metric_ignored_when_filter_unset(self):
        assert screener._passes_filters({"ticker": "L", "trailing_pe": None}, self._args())

    def test_present_metric_compared(self):
        assert screener._passes_filters({"trailing_pe": 15.0}, self._args(max_pe=20))
        assert not screener._passes_filters({"trailing_pe": 25.0}, self._args(max_pe=20))


class TestUnits:
    def test_scan_day_change_is_percent_points(self):
        row = _row_from_quote({"symbol": "MSFT", "regularMarketPrice": 512.8,
                               "regularMarketChangePercent": 0.42, "currency": "USD"})
        assert row[3] == "0.4%"

    @pytest.mark.parametrize("kind,val,expected", [
        ("cur", 4.4e12, "$4.40T"),        # listing currency (USD ADR)
        ("fin", 4.4e12, "TWD 4.40T"),     # reporting currency
        ("eps", 13.55, "$13.55"),
        ("pct", 0.0088, "0.9%"),          # shortPercentOfFloat is a fraction
        ("pct", 1.4875, "148.8%"),        # ROE above 100%
        ("pct_points", 0.89, "0.9%"),     # dividendYield is percent points
        ("int", 7679.0, "7,679"),
        ("x1", None, "N/A"),
    ])
    def test_ticker_metric_kinds(self, kind, val, expected):
        assert _fmt(kind, val, "USD", "TWD") == expected

    def test_pandas_missing_values_become_none(self):
        # Yahoo's insider-purchase summary carries pd.NA (crashed fmt_num before)
        import pandas as pd

        from finresearch.yfinance_cmd import _safe
        assert _safe(pd.NA) is None and _safe(pd.NaT) is None
        assert _fmt("shares", _safe(pd.NA), "USD", "USD") == "N/A"
