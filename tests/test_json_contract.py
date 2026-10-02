"""The machine contract: every command takes --json, stdout is one JSON
document, errors are one stderr line + exit 1, usage errors exit 2."""

import argparse
import json

import pytest

from finresearch import cli


def _leaves(parser, prefix=()):
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        yield prefix, parser
        return
    for name, sp in subs[0].choices.items():
        yield from _leaves(sp, prefix + (name,))


def run(capsys, *argv):
    """Run the CLI in-process -> (exit code, stdout, stderr)."""
    try:
        cli.main(list(argv))
        code = 0
    except SystemExit as e:
        code = e.code or 0
    out = capsys.readouterr()
    return code, out.out, out.err


class TestEveryCommandHasJson:
    def test_all_leaf_commands_accept_json(self):
        parser, _ = cli.build_parser()
        missing = []
        for path, sp in _leaves(parser):
            opts = {o for a in sp._actions for o in a.option_strings}
            if "--json" not in opts:
                missing.append(" ".join(path))
        assert missing == []

    def test_gappers_json_alias(self):
        parser, _ = cli.build_parser()
        assert parser.parse_args(["gappers", "--json"]).output_format == "json"
        assert parser.parse_args(["gappers", "--format", "json"]).output_format == "json"


class TestNewJsonOutputs:
    def test_fomc_calendar(self, capsys):
        code, out, _ = run(capsys, "fomc", "calendar", "--json")
        data = json.loads(out)
        assert code == 0 and data["meetings"] and "next_meeting" in data

    def test_fred_list_needs_no_key(self, capsys, monkeypatch, tmp_path):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.setenv("FINRESEARCH_CONFIG_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        code, out, _ = run(capsys, "fred", "list", "--json")
        data = json.loads(out)
        assert code == 0
        assert data["aliases"]["cpi_yoy"] == {"series_id": "CPIAUCSL", "transform": "pc1"}
        assert "Inflation" in data["categories"]

    def test_transcript(self, capsys):
        code, out, _ = run(capsys, "transcript", "aapl", "--json")
        assert json.loads(out)["transcripts_url"].endswith("/AAPL/earnings/transcripts")

    def test_fred_dashboard_and_yield_curve(self, capsys, monkeypatch):
        from finresearch import fred
        monkeypatch.setenv("FRED_API_KEY", "test")

        def fake_many(sids, key, n=10):
            return [{"title": f"T {s}", "units": "Percent", "frequency": "Daily",
                     "observations": [{"date": "2099-01-01", "value": "4.00"},
                                      {"date": "2099-01-02", "value": "4.10"}]}
                    for s in sids]
        monkeypatch.setattr(fred, "_fetch_latest_many", fake_many)
        code, out, _ = run(capsys, "fred", "dashboard", "--group", "rates", "--json")
        pt = json.loads(out)["groups"]["rates"][0]
        assert code == 0 and pt["value"] == 4.1 and pt["change"] == 0.1
        code, out, _ = run(capsys, "fred", "yield_curve", "--json")
        data = json.loads(out)
        assert len(data["curve"]) == 9 and data["spreads_pct"]["10Y-2Y"] == 0.0
        assert data["inverted"]["10Y-2Y"] is False

    def test_13f_who_and_diff(self, capsys, monkeypatch):
        from finresearch import form13f, form13f_diff
        monkeypatch.setattr(form13f, "who_holds", lambda name, limit=25: {
            "total_raw_hits": {"value": 1}, "filers": [{"cik": "1", "filer": "F"}]})
        monkeypatch.setattr(form13f_diff, "compute_diff",
                            lambda words, limit=15, min_shares=None: [{"action": "ADDED"}])
        code, out, _ = run(capsys, "13f", "who", "nvidia", "corp", "--json")
        assert code == 0 and json.loads(out)["issuer"] == "NVIDIA CORP"
        code, out, _ = run(capsys, "13f", "diff", "nvidia", "corp", "--json")
        assert json.loads(out) == {"issuer": "NVIDIA CORP", "rows": [{"action": "ADDED"}]}

    def test_sec_modes(self, capsys, monkeypatch):
        from finresearch import sec_edgar
        monkeypatch.setattr(sec_edgar, "find_cik", lambda t: ("0000000001", "TEST CO"))
        facts = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
            {"start": "2098-01-01", "end": "2098-12-31", "val": 5, "form": "10-K"}]}}}}}
        concept = {"units": {"USD/shares": [{"end": "2098-12-31", "val": 1.5, "fy": 2098}]}}
        subs = {"filings": {"recent": {"form": ["10-K"], "filingDate": ["2099-01-01"],
                                       "accessionNumber": ["a"], "primaryDocument": ["d.htm"]}}}
        monkeypatch.setattr(sec_edgar, "sec_get", lambda url: (
            facts if "companyfacts" in url else concept if "companyconcept" in url else subs))
        _, out, _ = run(capsys, "sec", "TEST", "--json")
        net = [f for f in json.loads(out)["facts"] if f["tag"] == "NetIncomeLoss"][0]
        assert net["value"] == 5 and net["period_end"] == "2098-12-31"
        _, out, _ = run(capsys, "sec", "TEST", "--concept", "eps", "--json")
        data = json.loads(out)
        assert data["unit"] == "USD/shares" and data["observations"][0]["fiscal_year"] == 2098
        _, out, _ = run(capsys, "sec", "TEST", "--type", "10-K", "--json")
        assert json.loads(out)["filings"][0]["accession"] == "a"

    def test_compare_records_and_errors(self, capsys, monkeypatch):
        from types import SimpleNamespace

        from finresearch import yfinance_cmd
        infos = {"GOOD": {"quoteType": "EQUITY", "currency": "USD", "shortName": "Good",
                          "currentPrice": 10.0, "totalRevenue": 5e9},
                 "BAD": {"trailingPegRatio": None}}
        monkeypatch.setattr(yfinance_cmd.yf, "Ticker", lambda s: SimpleNamespace(info=infos[s]))
        monkeypatch.setattr(yfinance_cmd.time, "sleep", lambda s: None)
        code, out, _ = run(capsys, "compare", "GOOD", "BAD", "--json")
        good, bad = json.loads(out)
        assert code == 0 and good["price"] == 10.0 and good["financial_currency"] == "USD"
        assert bad == {"ticker": "BAD", "error": "no Yahoo Finance quote"}
        code, out, err = run(capsys, "compare", "BAD", "--json")
        assert code == 1 and out == "" and "no data for any ticker" in err


class TestErrorContract:
    def test_unknown_ticker_is_exit_1_on_stderr(self, capsys, monkeypatch):
        from finresearch import insiders
        monkeypatch.setattr(insiders, "find_cik", lambda t: (None, None))
        code, out, err = run(capsys, "insider", "detail", "NOPE", "--json")
        assert code == 1 and out == ""
        assert err.startswith("finresearch: error:") and "NOPE" in err

    def test_no_resolvable_tickers_is_an_error_partial_is_a_warning(self, capsys, monkeypatch):
        from finresearch import sec_edgar
        monkeypatch.setattr(sec_edgar, "resolve_cik", lambda t: "1" if t == "GOOD" else None)
        assert sec_edgar.resolve_ciks(["GOOD", "BAD"]) == [("GOOD", "1")]
        assert "[skip] BAD" in capsys.readouterr().err
        with pytest.raises(SystemExit) as e:
            sec_edgar.resolve_ciks(["BAD"])
        assert e.value.code == 1

    def test_unknown_scan_template(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("FINRESEARCH_CONFIG_DIR", str(tmp_path))
        code, out, err = run(capsys, "scan", "nosuchscan", "--json")
        assert code == 1 and out == "" and "no scan template 'nosuchscan'" in err

    def test_scan_template_listing_as_json(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("FINRESEARCH_CONFIG_DIR", str(tmp_path))
        (tmp_path / "scans.toml").write_text('[mine]\ndescription = "d"\npe-max = 10\n')
        code, out, _ = run(capsys, "scan", "--json")
        tpl = json.loads(out)["templates"]["mine"]
        assert code == 0 and tpl == {"description": "d", "valid": True, "config": {"pe-max": 10}}

    def test_unexpected_exception_is_one_redacted_line(self, capsys, monkeypatch):
        from finresearch import transcript

        def boom(args):
            raise RuntimeError("GET https://x/y?series_id=A&api_key=SECRET123 failed")
        monkeypatch.setattr(transcript, "cmd_transcript", boom)
        monkeypatch.delenv("FINRESEARCH_DEBUG", raising=False)
        code, out, err = run(capsys, "transcript", "AAPL")
        assert code == 1 and out == ""
        assert err.count("\n") == 1 and "SECRET123" not in err and "api_key=***" in err

    def test_debug_env_reraises(self, monkeypatch):
        from finresearch import transcript

        def boom(args):
            raise RuntimeError("boom")
        monkeypatch.setattr(transcript, "cmd_transcript", boom)
        monkeypatch.setenv("FINRESEARCH_DEBUG", "1")
        with pytest.raises(RuntimeError):
            cli.main(["transcript", "AAPL"])

    def test_usage_errors_exit_2(self, capsys):
        assert run(capsys, "insider")[0] == 2   # family without subcommand
        assert run(capsys)[0] == 2              # no command at all
        assert run(capsys, "ticker")[0] == 2    # missing argument (argparse)
