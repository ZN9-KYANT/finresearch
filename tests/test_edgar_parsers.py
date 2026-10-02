"""Tests for SEC XML parsing (Form 4 + 13F) — pure logic, fixtures only."""

from finresearch.form13f import detect_value_scale, parse_13f_information_table
from finresearch.insiders import classify, parse_form4_xml


class TestForm4Parser:
    def test_parses_issuer_and_insider(self, form4_xml):
        rec = parse_form4_xml(form4_xml)
        assert rec["issuer"] == "Test Issuer, Inc."
        assert rec["issuer_cik"] == "0001326801"
        assert rec["insider"] == "DOE JANE Q"

    def test_roles_accept_true_and_numeric_flags(self, form4_xml):
        rec = parse_form4_xml(form4_xml)
        # isDirector=1, isOfficer=true, 10pct=0, other=false
        assert any(r == "Director" for r in rec["roles"])
        assert any(r.startswith("Officer:") and "Chief Financial" in r for r in rec["roles"])
        assert not any("10%Owner" in r for r in rec["roles"])
        assert not any(r == "Other" for r in rec["roles"])

    def test_non_derivative_transaction_fields(self, form4_xml):
        rec = parse_form4_xml(form4_xml)
        nonderiv = [t for t in rec["transactions"] if t["kind"] == "non-derivative"]
        assert len(nonderiv) == 1
        tx = nonderiv[0]
        assert tx["date"] == "2026-09-28"
        assert tx["shares"] == "25000"
        assert tx["price"] == "123.45"
        assert tx["acquired_disposed"] == "D"
        assert tx["post_shares"] == "100000"

    def test_derivative_transaction_captured_with_kind(self, form4_xml):
        rec = parse_form4_xml(form4_xml)
        deriv = [t for t in rec["transactions"] if t["kind"] == "derivative"]
        assert len(deriv) == 1

    def test_namespace_agnostic(self, form4_xml_no_ns):
        rec = parse_form4_xml(form4_xml_no_ns)
        assert rec["issuer"] == "Test Issuer, Inc."
        assert len(rec["transactions"]) == 2

    def test_classify_buckets_by_code(self, form4_xml):
        rec = parse_form4_xml(form4_xml)
        buys, sells, other = classify(rec)
        assert buys == [] and other == []
        assert len(sells) == 1
        tx = sells[0]
        assert tx["value"] == 25000 * 123.45

    def test_classify_ignores_derivative_legs(self, form4_xml):
        rec = parse_form4_xml(form4_xml)
        buys, sells, other = classify(rec)
        # fixture has 1 non-deriv SELL + 1 derivative option: only the SELL may surface
        assert len(buys) == 0 and len(sells) == 1 and len(other) == 0
        assert all(t["kind"] == "non-derivative" for t in buys + sells + other)


class TestForm13FParser:
    def test_parses_rows(self, form13f_xml):
        parsed = parse_13f_information_table(form13f_xml)
        assert len(parsed["rows"]) == 2
        r0 = parsed["rows"][0]
        assert r0["nameOfIssuer"] == "ALLY FINL INC"
        assert r0["cusip"] == "02005N100"
        assert r0["value"] == "577211815"
        assert r0["shares"] == "12561737"
        assert r0["putCall"] is None

    def test_put_call_row(self, form13f_xml):
        parsed = parse_13f_information_table(form13f_xml)
        assert parsed["rows"][1]["putCall"] == "Put"


class TestValueScaleDetection:
    ROWS_RAW_DOLLARS = [{
        "nameOfIssuer": "TESTCO INC", "shares": "1000", "value": "338250",
    }]

    def test_detects_raw_dollars(self, known_issuer):
        # 338250 / 1000 = $338.25/share = the real price -> raw dollars
        scale, why = detect_value_scale(self.ROWS_RAW_DOLLARS,
                                        price_lookup=lambda t: 338.25)
        assert scale == 1
        assert "raw dollars" in why

    def test_detects_raw_dollars_for_sub_100_dollar_stock(self, known_issuer):
        # regression: $50 stock in raw dollars was misread as thousands (1000x)
        rows = [{"nameOfIssuer": "TESTCO INC", "shares": "100000", "value": "5000000"}]
        scale, why = detect_value_scale(rows, price_lookup=lambda t: 50.0)
        assert scale == 1
        assert "raw dollars" in why

    def test_detects_thousands(self, known_issuer):
        # 1000 sh x $338.25 = $338,250 reported as 338 (thousands)
        rows = [{"nameOfIssuer": "TESTCO INC", "shares": "1000", "value": "338"}]
        scale, why = detect_value_scale(rows, price_lookup=lambda t: 338.25)
        assert scale == 1000
        assert "thousands" in why

    def test_unpriceable_falls_back_to_filing_date(self, known_issuer):
        scale, why = detect_value_scale(self.ROWS_RAW_DOLLARS,
                                        price_lookup=lambda t: None, filed="2026-08-14")
        assert scale == 1
        assert "price unavailable" in why
        scale, _ = detect_value_scale(self.ROWS_RAW_DOLLARS,
                                      price_lookup=lambda t: None, filed="2022-11-14")
        assert scale == 1000

    def test_price_lookup_import_error_falls_back_to_filing_date(self, known_issuer):
        def broken(t):
            raise ImportError("no yfinance")
        scale, why = detect_value_scale(self.ROWS_RAW_DOLLARS, price_lookup=broken,
                                        filed="2021-05-15")
        assert scale == 1000
        assert "yfinance unavailable" in why

    def test_inconclusive_price_check_uses_filing_date(self, known_issuer):
        # implied $338.25 or $338,250 vs a real $3: neither within 10x
        scale, why = detect_value_scale(self.ROWS_RAW_DOLLARS,
                                        price_lookup=lambda t: 3.0, filed="2026-08-14")
        assert scale == 1
        assert "inconclusive" in why

    def test_option_and_bond_rows_are_not_priced(self, known_issuer):
        rows = [
            {"nameOfIssuer": "TESTCO INC", "shares": "10", "value": "999999999",
             "putCall": "Put"},
            {"nameOfIssuer": "TESTCO INC", "shares": "10", "value": "999999998",
             "type": "PRN"},
            {"nameOfIssuer": "TESTCO INC", "shares": "1000", "value": "338"},
        ]
        scale, _ = detect_value_scale(rows, price_lookup=lambda t: 338.25)
        assert scale == 1000  # decided by the SH row, not the bigger option/bond rows
