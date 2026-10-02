"""Insider trading commands — SEC EDGAR Form 4 (native, no third-party API).

Data flow:
  1. data.sec.gov submissions JSON  -> Form 4 accessions for a CIK within --days
  2. www.sec.gov filing index.json  -> locate the primary XML document
  3. XML parse (namespace-agnostic) -> structured transactions

Transaction codes (SEC Form 4 Table I):
  P = open-market purchase      S = open-market sale
  A = grant/award               M = option exercise (cashless or same-day sale)
  F = tax withholding           G = gift
  C = stock conversion          X = option exercise (per filing text)
  W = acquisition/disposition by will/inheritance

Only P and S are treated as open-market signals; everything else is context.
"""

import xml.etree.ElementTree as ET

from .config import load_watchlist
from .edgar_common import (
    child_text,
    fetch_file,
    filing_index,
    find_all,
    first,
    list_filings,
    to_float,
)
from .formatting import fmt_num, fmt_shares, print_table
from .output import emit_json, fail, warn
from .sec_edgar import find_cik

CODE_LEGEND = {
    "P": "open-market purchase",
    "S": "open-market sale",
    "A": "grant/award",
    "M": "option exercise",
    "F": "tax withholding",
    "G": "gift",
    "C": "conversion",
    "X": "option exercise",
    "W": "inheritance disposition",
}


def parse_form4_xml(content):
    """Parse a Form 4 XML body into a dict. Namespace-agnostic by design."""
    root = ET.fromstring(content)

    issuer_el = first(root, "issuer")
    issuer = child_text(issuer_el, "issuerName") if issuer_el is not None else None
    issuer_cik = child_text(issuer_el, "issuerCik") if issuer_el is not None else None

    owner_el = first(root, "reportingOwner")
    owner_id = first(owner_el, "reportingOwnerId") if owner_el is not None else None
    insider = child_text(owner_id, "rptOwnerName") if owner_id is not None else None
    rel = first(owner_el, "reportingOwnerRelationship") if owner_el is not None else None
    roles = []
    if rel is not None:
        if _truthy(child_text(rel, "isDirector")):
            roles.append("Director")
        if _truthy(child_text(rel, "isOfficer")):
            roles.append("Officer" + (f":{child_text(rel, 'officerTitle')}" if child_text(rel, "officerTitle") else ""))
        if _truthy(child_text(rel, "isTenPercentOwner")):
            roles.append("10%Owner")
        if _truthy(child_text(rel, "isOther")):
            roles.append("Other")

    txs = []
    table_tx_tag = {
        "nonDerivativeTable": "nonDerivativeTransaction",
        "derivativeTable": "derivativeTransaction",
    }
    for table_tag, tx_tag in table_tx_tag.items():
        table = first(root, table_tag)
        if table is None:
            continue
        kind = "non-derivative" if table_tag == "nonDerivativeTable" else "derivative"
        for tx in find_all(table, tx_tag):
            sec = child_text(tx, "securityTitle", "value")
            ad_el = first(tx, "transactionAquiredDisposedCode")
            txs.append({
                "kind": kind,
                "security": (sec or "")[:24],
                "code": child_text(tx, "transactionCoding", "transactionCode"),
                "date": child_text(tx, "transactionDate", "value"),
                "shares": child_text(tx, "transactionShares", "value"),
                "price": child_text(tx, "transactionPricePerShare", "value"),
                "acquired_disposed": child_text(ad_el, "value") if ad_el is not None else None,
                "post_shares": child_text(tx, "postTransactionAmounts", "sharesOwnedFollowingTransaction", "value"),
                "direct": child_text(tx, "ownershipNature", "directOrIndirectOwnership", "value"),
            })
    return {
        "issuer": issuer,
        "issuer_cik": issuer_cik,
        "insider": insider,
        "roles": roles,
        "transactions": txs,
    }


def _truthy(v):
    """Form 4 relationship flags may arrive as 'true'/'1'/'yes'."""
    return str(v).strip().lower() in {"true", "1", "yes"}


def _fmt_price(s):
    n = to_float(s)
    return f"{n:.2f}" if n is not None else "-"


# ------------------------------------------------------------- EDGAR lookups

def list_form4_filings(cik10, days):
    """Form 4 accession numbers + dates for a CIK within N days."""
    return list_filings(cik10, ["4"], days=days, prefix_match=False)


def fetch_form4_record(filing, cik10):
    """Fetch + parse one Form 4 filing. Returns parsed dict with filing metadata."""
    xml_name = filing.get("primary_doc")
    # submissions API often points at the styled viewer (xslF345X0x/...): not raw XML.
    # Trust only a bare filename; otherwise resolve via the filing directory index.
    if not xml_name or "/" in xml_name:
        try:
            cands = [n for n in filing_index(cik10, filing["accession"])
                     if n.endswith(".xml") and "/" not in n]
        except Exception:
            cands = []
        xml_name = next((n for n in cands if "primary" in n.lower()),
                        max(cands, key=len) if cands else None)
    if not xml_name:
        return None
    try:
        parsed = parse_form4_xml(fetch_file(cik10, filing["accession"], xml_name))
    except ET.ParseError:
        return None
    parsed["accession"] = filing["accession"]
    parsed["filing_date"] = filing["filing_date"]
    return parsed


def resolve_tickers(tickers):
    """Resolve tickers to CIKs using the shared company_tickers cache."""
    resolved = []
    for t in tickers:
        cik, title = find_cik(t)
        if cik:
            resolved.append((t.upper(), cik, title))
        else:
            warn(f"  [skip] {t}: no SEC CIK mapping found")
    if tickers and not resolved:
        fail(f"no SEC CIK found for: {', '.join(tickers)}")
    return resolved


# ------------------------------------------------------------------ analysis

def classify(parsed):
    """Roll a parsed filing up into buy/sell/other buckets with $ values."""
    buys, sells, other = [], [], []
    for tx in parsed["transactions"]:
        if tx["kind"] != "non-derivative":
            continue  # derivative leg kept out of headline signals
        shares = to_float(tx["shares"])
        price = to_float(tx["price"])
        value = shares * price if shares and price else None
        row = dict(tx, value=value)
        code = (tx["code"] or "?").upper()
        if code == "P":
            buys.append(row)
        elif code == "S":
            sells.append(row)
        else:
            other.append(row)
    return buys, sells, other


def scan_tickers(tickers, days, min_value=None):
    """Scan insider activity for a list of tickers. Returns list of result dicts."""
    results = []
    for ticker, cik, title in resolve_tickers(tickers):
        filings = list_form4_filings(cik, days)
        rows = []
        for f in filings:
            rec = fetch_form4_record(f, cik)
            if rec is None:
                continue
            buys, sells, _other = classify(rec)
            for bucket, side in ((buys, "BUY"), (sells, "SELL")):
                for tx in bucket:
                    if min_value and (tx["value"] or 0) < min_value:
                        continue
                    rows.append({
                        "ticker": ticker,
                        "insider": rec["insider"],
                        "roles": ",".join(rec["roles"]) or "-",
                        "side": side,
                        "code": tx["code"],
                        "date": tx["date"] or rec["filing_date"],
                        "shares": tx["shares"],
                        "price": tx["price"],
                        "value": tx["value"],
                    })
        results.append({"ticker": ticker, "company": title, "transactions": rows})
    return results


# ------------------------------------------------------------------ commands

def _print_scan(results):
    interesting = [r for r in results if r["transactions"]]
    if not interesting:
        print("No open-market insider buys/sells found in the period.")
        return
    for r in interesting:
        print(f"\n=== {r['ticker']} — {r['company']} ===")
        header = ["date", "insider", "roles", "side", "code", "shares", "price", "value"]
        table = []
        for tx in r["transactions"]:
            table.append([
                tx["date"],
                (tx["insider"] or "")[:28],
                tx["roles"][:20],
                tx["side"],
                tx["code"],
                fmt_shares(tx["shares"]),
                _fmt_price(tx["price"]),
                fmt_num(tx["value"]) if tx["value"] else "-",
            ])
        table.sort(key=lambda row: row[0], reverse=True)
        print_table(header, table)
    print("\nCodes: P=open-market buy  S=open-market sale  (context codes filtered out)")


def _print_detail(ticker, records):
    if not records:
        print(f"No Form 4 filings for {ticker} in the period.")
        return
    header = ["date", "insider", "roles", "code", "meaning", "security", "shares", "price", "post"]
    table = []
    for rec in records:
        for tx in rec["transactions"]:
            code = (tx["code"] or "?").upper()
            table.append([
                tx["date"] or rec["filing_date"],
                (rec["insider"] or "")[:26],
                ",".join(rec["roles"])[:24] or "-",
                code,
                CODE_LEGEND.get(code, "-"),
                tx["security"],
                fmt_shares(tx["shares"]),
                _fmt_price(tx["price"]),
                fmt_shares(tx["post_shares"]),
            ])
    table.sort(key=lambda row: row[0], reverse=True)
    print_table(header, table)
    buys = sum(1 for row in table if row[3] == "P")
    sells = sum(1 for row in table if row[3] == "S")
    print(f"\n{len(records)} filings | {buys} open-market buy txs | {sells} open-market sell txs")
    print("Codes: P=buy S=sale A=grant M=exercise F=withholding G=gift")


def cmd_insider(args):
    """Entry point for `finresearch insider`."""
    if args.insider_cmd == "detail":
        ticker = args.ticker.upper()
        cik, title = find_cik(ticker)
        if not cik:
            fail(f"ticker {ticker} not found in SEC EDGAR")
        filings = list_form4_filings(cik, args.days)
        records = []
        for f in filings:
            rec = fetch_form4_record(f, cik)
            if rec:
                records.append(rec)
        if args.json:
            out = {"ticker": ticker, "company": title, "filings": records}
            emit_json(out)
        else:
            print(f"=== {ticker} — {title} — Form 4 filings, last {args.days} days ===")
            _print_detail(ticker, records)
        return

    # scan mode
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = load_watchlist()
    results = scan_tickers(tickers, args.days, args.min_value)
    if args.json:
        emit_json(results)
    else:
        _print_scan(results)

