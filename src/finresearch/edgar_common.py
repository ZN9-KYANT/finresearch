"""Shared SEC EDGAR plumbing: the ONE polite HTTP fetcher every EDGAR module
uses, submissions listing by form family, filing-directory lookup, document
retrieval, and namespace-agnostic XML helpers.

House conventions:
- EDGAR fair-access UA with a deliverable contact email (SEC 403s malformed UAs).
- >10 req/s compliance via a single process-wide fetch gap.
- Archives host for filing documents, data.sec.gov for JSON APIs.
"""

import functools
import json
import re
import time
import urllib.request

from .config import user_agent

SEC_USER_AGENT = user_agent()
DATA_BASE = "https://data.sec.gov"
ARC_BASE = "https://www.sec.gov/Archives"
_REQUEST_GAP = 0.25  # >10 req/s compliance
_LAST_FETCH = [0.0]


def _get(url, timeout=25):
    """Polite GET: bytes, with UA + process-wide rate gap."""
    wait = _REQUEST_GAP - (time.monotonic() - _LAST_FETCH[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_FETCH[0] = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(url, timeout=25):
    return json.loads(_get(url, timeout=timeout))


def to_float(s):
    """'1,234.5' / 1234.5 / None -> float or None."""
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ XML helpers

def _local(el):
    return el.tag.split("}")[-1] if "}" in el.tag else el.tag


def find_all(el, name):
    """Descendants of el (not el itself) with this local tag name, doc order."""
    if el is None:
        return []
    return [d for d in el.iter() if d is not el and _local(d) == name]


def first(el, name):
    """First descendant with this local tag name, or None."""
    if el is None:
        return None
    return next((d for d in el.iter() if d is not el and _local(d) == name), None)


def child_text(el, *path):
    """Walk nested elements by local name; stripped final .text or None."""
    cur = el
    for step in path:
        cur = first(cur, step)
        if cur is None:
            return None
    return cur.text.strip() if cur.text else None


# --------------------------------------------------------------- filings

def _doc_text(content):
    """Bytes -> decoded HTML/text (filings are win-1252-ish; forgiving decode)."""
    if isinstance(content, str):
        return content
    return content.decode("utf-8", "ignore")


def strip_tags(raw, limit=120_000):
    """HTML -> rough text, unescaped, whitespace-normalized, head-trimmed."""
    head = _doc_text(raw)[:limit]
    head = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", head, flags=re.S | re.I)
    head = re.sub(r"<[^>]+>", " ", head)
    head = re.sub(r"&nbsp;?", " ", head)
    head = re.sub(r"&amp;", "&", head)
    head = re.sub(r"[ \t\r\xa0]+", " ", head)
    return head


def submissions(cik10):
    """The issuer's submissions feed 'recent' block (columnar dict of lists)."""
    return _get_json(f"{DATA_BASE}/submissions/CIK{cik10}.json")["filings"]["recent"]


def list_filings(cik10, forms, days=365, prefix_match=True, regex=None):
    """Filings by exact form code / prefix, or by a regex on the form name
    (EDGAR spells the same family differently: 'SC 13G/A', 'SCHEDULE 13G/A').
    Returns [{form, filing_date, report_date, accession, primary_doc, items}],
    newest first. `items` is the submissions feed's 8-K item list ('2.02,9.01')."""
    rec = submissions(cik10)
    n = len(rec["form"])

    def col(name):
        return rec.get(name) or [None] * n

    cutoff = time.time() - days * 86400 if days is not None else None
    rx = re.compile(regex) if regex else None
    out = []
    for i, form in enumerate(rec["form"]):
        if rx is not None:
            ok = bool(rx.search(form))
        else:
            ok = any(form == f or (prefix_match and form.startswith(f)) for f in forms)
        if not ok:
            continue
        if cutoff is not None:
            try:
                ts = time.mktime(time.strptime(rec["filingDate"][i], "%Y-%m-%d"))
            except (ValueError, KeyError, TypeError):
                continue
            if ts < cutoff:
                continue
        out.append({
            "form": form,
            "filing_date": rec["filingDate"][i],
            "report_date": col("reportDate")[i],
            "accession": rec["accessionNumber"][i],
            "primary_doc": col("primaryDocument")[i],
            "items": col("items")[i] or "",
        })
    out.sort(key=lambda r: r["filing_date"], reverse=True)
    return out


def _filing_dir(cik10, accession):
    return f"{ARC_BASE}/edgar/data/{int(cik10)}/{accession.replace('-', '')}"


@functools.lru_cache(maxsize=256)
def filing_index(cik10, accession):
    """Bare filenames in a filing directory (cached: callers share one fetch)."""
    try:
        items = _get_json(f"{_filing_dir(cik10, accession)}/index.json")
        return tuple(it["name"] for it in items["directory"]["item"])
    except (ValueError, KeyError):
        return ()


def fetch_file(cik10, accession, name, timeout=25):
    """Raw bytes of one file inside a filing directory."""
    return _get(f"{_filing_dir(cik10, accession)}/{name}", timeout=timeout)


_JUNK_PAT = re.compile(
    r"(index-headers?\.html?$|^index\.|^poster\.|^graphic|\.gif$|\.jpg$|\.png$|\.sgml$|_headers?\.)",
    re.IGNORECASE)
_TEXT_DOC = (".htm", ".html", ".txt")


def filing_doc_name(cik10, accession, prefer_primary=None):
    """Pick the parseable primary doc from a filing directory.
    prefer_primary: the submissions-API primaryDocument — trusted without a
    directory fetch when it is a bare text/HTML filename (xsl viewer paths
    like 'xslF345X05/doc.xml' are not). Returns a bare filename or None."""
    if (prefer_primary and "/" not in prefer_primary
            and prefer_primary.lower().endswith(_TEXT_DOC)):
        return prefer_primary
    names = filing_index(cik10, accession)
    bare = [n for n in names
            if "/" not in n and n.lower().endswith(_TEXT_DOC) and not _JUNK_PAT.search(n)]
    for n in bare:
        if "primary" in n.lower():
            return n
    return bare[0] if bare else None


def fetch_doc_text(cik10, accession, prefer_primary=None):
    """Primary doc of a filing as plain text. None if unavailable."""
    name = filing_doc_name(cik10, accession, prefer_primary=prefer_primary)
    if not name:
        return None
    try:
        return strip_tags(fetch_file(cik10, accession, name))
    except Exception:
        return None
