"""finresearch scan — FULL-MARKET stock screening via Yahoo's server-side engine.

Unlike `screen` (which filters a user-supplied ticker list), `scan` queries the
entire market server-side (yfinance.screener: EquityQuery + screen) — no 10k-ticker
looping. ~90 fields supported (price/vol/PE/PEG/margins/growth/roe/short-%float/
days-to-cover/institutional %/dividend yield/debt/liquidity + region/sector/industry).

UNIT CONTRACT (verified live): ratio fields arrive in PERCENT — netincomemargin
and forward_dividend_yield filters take percent numbers (margin>20 keeps ~2.3k of
~10k names, not ~0). price/cap/raw numbers are plain. The API's `total` echoes the
true match count; `count` is the page size.
"""

import json
import os
import sys

from .config import config_dir
from .formatting import fmt_num, fmt_pct, print_table

# user filter name -> (EquityQuery field, unit kind)
# unit kinds: 'price' (raw), 'percent' (field is %), 'raw'
FIELD_MAP = {
    "price": ("intradayprice", "price"),
    "mktcap": ("intradaymarketcap", "price"),
    "avgvol": ("avgdailyvol3m", "raw"),
    "volume": ("dayvolume", "raw"),
    "day-chg": ("intradaypricechange", "percent"),
    "pe": ("peratio.lasttwelvemonths", "raw"),
    "peg": ("pegratio_5y", "raw"),
    "netmargin": ("netincomemargin.lasttwelvemonths", "percent"),
    "grossmargin": ("grossprofitmargin.lasttwelvemonths", "percent"),
    "ebitda-margin": ("ebitdamargin.lasttwelvemonths", "percent"),
    "revgrowth": ("totalrevenues1yrgrowth.lasttwelvemonths", "percent"),
    "epsgrowth": ("epsgrowth.lasttwelvemonths", "percent"),
    "roe": ("returnonequity.lasttwelvemonths", "percent"),
    "shortfloat": ("short_percentage_of_float.value", "percent"),
    "dtc": ("days_to_cover_short.value", "raw"),
    "inst-held": ("pctheldinst", "percent"),
    "insider-held": ("pctheldinsider", "percent"),
    "divyield": ("forward_dividend_yield", "percent"),
    "debteq": ("totaldebtequity.lasttwelvemonths", "raw"),
    "quickratio": ("quickratio.lasttwelvemonths", "raw"),
    "altmanz": ("altmanzscoreusingtheaveragestockinformationforaperiod.lasttwelvemonths", "raw"),
    "beta": ("beta", "raw"),
    "pb": ("pricebookratio.quarterly", "raw"),
    "perf-52w": ("fiftytwowkpercentchange", "percent"),
}

# client-side post-filters (Yahoo can't query distance-from-52w-extreme
# server-side — its 52w fields are absolute prices — so these refine the
# returned page; values are FRACTIONS: within-high 0.25 = within 25%)
POST_FILTERS = {
    "within-high": "fiftyTwoWeekHighChangePercent",  # keep >= -N
    "below-high": "fiftyTwoWeekHighChangePercent",   # keep <= -N
    "off-low": "fiftyTwoWeekLowChangePercent",       # keep >= +N
}

SORT_MAP = {
    "mktcap": "intradaymarketcap",
    "price": "intradayprice",
    "day-chg": "percentchange",
    "volume": "avgdailyvol3m",
    "pe": "peratio.lasttwelvemonths",
    "peg": "pegratio_5y",
    "netmargin": "netincomemargin.lasttwelvemonths",
    "revgrowth": "totalrevenues1yrgrowth.lasttwelvemonths",
    "shortfloat": "short_percentage_of_float.value",
    "perf-52w": "fiftytwowkpercentchange",
}

# ---------------------------------------------------------------------------
# Named scan templates (~/.config/finresearch/scans.toml)
#
# Keys mirror CLI flag names EXACTLY (without --):
#   [squeeze]
#   description = "high short %, days-to-cover piling up"
#   region = "us"
#   price = [2, 50]          # range field: [lo, hi]
#   shortfloat-min = 15      # ratio fields: percent numbers (same as CLI)
#   sort = "shortfloat"
# ---------------------------------------------------------------------------

MIN_SUFFIX = "-min"
MAX_SUFFIX = "-max"

SCAN_DEFAULTS = {}  # attr -> parser default, captured at register() time


def scans_path():
    return config_dir() / "scans.toml"


def _valid_keys():
    keys = {"region", "sector", "industry", "sort", "limit", "ascending"}
    keys.update(POST_FILTERS)
    for name, (_field, unit) in FIELD_MAP.items():
        if unit == "price":
            keys.add(name)
        else:
            keys.add(f"{name}{MIN_SUFFIX}")
            keys.add(f"{name}{MAX_SUFFIX}")
    return keys


def post_filter(quotes, args):
    """Apply client-side 52w-extreme filters; returns (kept, dropped_count).
    Yahoo's server-side 52w query fields are absolute prices, so distance-from-
    high/low can't be expressed there — refine the page instead. The CLI takes
    positive fractions: --within-high 0.25 = within 25% of the 52-week high."""
    checks = []  # (payload_field, op, threshold)
    if getattr(args, "within_high", None) is not None:
        checks.append((POST_FILTERS["within-high"], "gte", -args.within_high))
    if getattr(args, "below_high", None) is not None:
        checks.append((POST_FILTERS["below-high"], "lte", -args.below_high))
    if getattr(args, "off_low", None) is not None:
        checks.append((POST_FILTERS["off-low"], "gte", args.off_low))
    if not checks:
        return quotes, 0

    def ok(qt):
        for field, op, thr in checks:
            v = qt.get(field)
            if v is None:
                return False
            if op == "gte" and not v >= thr:
                return False
            if op == "lte" and not v <= thr:
                return False
        return True

    kept = [qt for qt in quotes if ok(qt)]
    return kept, len(quotes) - len(kept)


def has_query(args):
    """True when any query/output flag differs from its parser default."""
    return any(getattr(args, k, None) != v for k, v in SCAN_DEFAULTS.items())


def _attr(key):
    return key.replace("-", "_")


def load_scans():
    """Parse scans.toml -> dict of templates ({} when absent/unparseable)."""
    try:
        import tomllib
    except ImportError:  # py3.10: stdlib tomllib is 3.11+, use tomli shim
        try:
            import tomli as tomllib
        except ImportError:
            print("WARNING: tomllib/tomli unavailable — scan templates disabled "
                  "(py>=3.11, or `uv pip install tomli` on 3.10)", file=sys.stderr)
            return {}
    p = scans_path()
    if not p.exists():
        return {}
    try:
        with open(p, "rb") as fh:
            data = tomllib.load(fh)
    except Exception as e:  # corrupt file: warn loudly, never crash the CLI
        print(f"WARNING: could not parse {p}: {e}", file=sys.stderr)
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def validate_template(name, tpl):
    """Unknown keys / bad shapes -> ValueError with a helpful message."""
    valid = _valid_keys()
    for key, value in (tpl or {}).items():
        if key == "description":
            continue
        if key not in valid:
            raise ValueError(
                f"unknown key '{key}' in scan template '{name}' "
                f"({scans_path()}). Valid keys: {', '.join(sorted(valid))}")
        if key in ("price", "mktcap"):
            if not (isinstance(value, list) and len(value) == 2):
                raise ValueError(
                    f"'{key}' in template '{name}' must be [lo, hi], got {value!r}")
    return tpl


def apply_template(args, tpl):
    """Overwrite args with template values UNLESS the CLI set them explicitly
    (CLI value still at its parser default => take the template's)."""
    for key, value in validate_template("template", tpl).items():
        if key == "description":
            continue
        attr = _attr(key)
        if getattr(args, attr, None) == SCAN_DEFAULTS.get(attr):
            setattr(args, attr, value)
    return args


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return json.dumps(str(value))  # basic string, ASCII-safe escaping


def _atomic_write(path, text):
    """Write via temp file + rename so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save_scan(name, args):
    """Append/replace template NAME from the EFFECTIVE args (merged cfg+CLI)."""
    p = scans_path()
    existing = load_scans()
    tpl = {}
    for key in sorted(_valid_keys()):
        val = getattr(args, _attr(key), None)
        if val is None:
            continue
        if key == "region" and val == "us":
            continue
        if key == "sort" and val == "mktcap":
            continue
        if key == "limit" and val == 20:
            continue
        if key == "ascending" and not val:
            continue
        if key in ("within-high", "below-high", "off-low") and not val:
            continue
        tpl[key] = val
    desc = getattr(args, "desc", None)
    if desc is None and name in existing:
        # desc loss on replace is never what the user wants — carry it
        desc = existing[name].get("description")
    if name in existing:
        existing[name] = {**tpl, "description": desc}
        lines = []
        for tname, body in existing.items():
            if lines:
                lines.append("")
            lines.append(f"[{tname}]")
            body = dict(body or {})
            if body.get("description"):
                lines.append(f"description = {_toml_value(body['description'])}")
                body = {k: v for k, v in body.items() if k != "description"}
            for k, v in sorted(body.items()):
                lines.append(f"{k} = {_toml_value(v)}")
        _atomic_write(p, "\n".join(lines) + "\n")
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        block = [f"[{name}]"]
        if desc:
            block.append(f"description = {_toml_value(desc)}")
        for k, v in sorted(tpl.items()):
            block.append(f"{k} = {_toml_value(v)}")
        with open(p, "a", encoding="utf-8") as fh:
            if p.stat().st_size:
                fh.write("\n")
            fh.write("\n".join(block) + "\n")
    return p


def list_scans():
    """Print the saved-template table; returns True when templates exist."""
    scans = load_scans()
    if not scans:
        return False
    rows = []
    for name, tpl in scans.items():
        try:
            validate_template(name, tpl)
        except ValueError:
            rows.append([name, "INVALID TEMPLATE (won't run)", "", ""])
            continue
        n_filters = sum(1 for k in tpl if k not in ("description", "region",
                                                    "sort", "limit"))
        rows.append([name, (tpl.get("description") or "")[:38],
                     tpl.get("region", "us"), f"{n_filters} filters"
                     + (f", sort {tpl['sort']}" if tpl.get("sort") else "")])
    print_table(["saved scan", "description", "region", "config"], rows)
    print(f"\nrun one: finresearch scan NAME   (file: {scans_path()})")
    return True


def filter_specs(args):
    """Parse argparse attrs -> [(field, op, value)]. Pure; unit-testable."""
    specs = []
    for name, (field, unit) in FIELD_MAP.items():
        if unit == "price":
            rng = getattr(args, name.replace("-", "_"), None)
            if rng:
                lo, hi = rng
                specs.append((field, "btwn", [lo, hi]))
            continue
        lo = getattr(args, name.replace("-", "_") + MIN_SUFFIX.replace("-", "_"), None)
        hi = getattr(args, name.replace("-", "_") + MAX_SUFFIX.replace("-", "_"), None)
        if lo is not None:
            specs.append((field, "gt" if unit in ("raw", "percent") else "gte", lo))
        if hi is not None:
            specs.append((field, "lt" if unit in ("raw", "percent") else "lte", hi))
    return specs


def _resolve_sector_or_industry(kind, user_input):
    """Fuzzy-match user text to Yahoo's vocabulary; raises with candidates."""
    from yfinance.screener.query import EQUITY_SCREENER_EQ_MAP
    valid = list(EQUITY_SCREENER_EQ_MAP.get(kind, {}))
    low = user_input.lower().strip()
    hits = [v for v in valid if low in str(v).lower()]
    if not hits:
        preview = ", ".join(sorted(map(str, valid))[:12])
        raise ValueError(
            f"no {kind} matching '{user_input}'. Yahoo vocabulary sample: {preview} ...")
    # several hits: the shortest wins heuristically (most specific user intent)
    hits.sort(key=len)
    return hits[0], hits


def run_scan(args):
    """Build the query, run yfinance.screen, return (total, quotes)."""
    from yfinance import EquityQuery
    from yfinance.screener import screen

    parts = [EquityQuery("eq", ["region", args.region])]
    for field, op, value in filter_specs(args):
        if op == "btwn":
            # Yahoo shape: ['btwn', [field, lo, hi]] (flat, 3 operands)
            parts.append(EquityQuery("btwn", [field] + list(value)))
        else:
            parts.append(EquityQuery(op, [field, value]))
    for kind, attr in (("sector", "sector"), ("industry", "industry")):
        raw = getattr(args, attr, None)
        if raw:
            match, hits = _resolve_sector_or_industry(kind, raw)
            parts.append(EquityQuery("eq", [kind, match]))
    q = EquityQuery("and", parts)

    sort_field = SORT_MAP.get(args.sort)
    size = max(1, min(args.limit, 250))
    res = screen(q, size=size, offset=0, count=True,
                 sortField=sort_field, sortAsc=bool(args.ascending))
    total = res.get("total")
    quotes = res.get("quotes", [])
    return total, quotes


def _row_from_quote(qt):
    cap = qt.get("marketCap")
    cur = qt.get("currency") or "USD"
    eps = qt.get("epsTrailingTwelveMonths")
    px = qt.get("regularMarketPrice")
    pe = (px / eps) if isinstance(px, (int, float)) and isinstance(eps, (int, float)) and eps else None
    return [
        qt.get("symbol", "?"),
        (qt.get("shortName") or qt.get("longName") or "")[:26],
        fmt_num(px, cur),
        fmt_pct(qt.get("regularMarketChangePercent"), percent_units=True),
        fmt_num(cap, cur),
        fmt_num(qt.get("regularMarketVolume"), "shares"),
        f"{pe:.1f}" if pe else "-",
        f"{qt['priceToBook']:.1f}" if isinstance(qt.get("priceToBook"), (int, float)) else "-",
    ]


def cmd_market_scan(args):
    """finresearch scan — discover stocks across the whole market by filters."""
    # template mode: config-first, CLI flags override
    if getattr(args, "name", None):
        scans = load_scans()
        if args.name not in scans and not getattr(args, "save", False):
            known = ", ".join(sorted(scans)) or "none saved yet"
            print(f"No scan template '{args.name}' (saved: {known}).")
            print(f"Create it: finresearch scan {args.name} --price 5 100 --save --desc '...'")
            return
        if args.name in scans:
            try:
                apply_template(args, scans[args.name])
            except ValueError as e:
                print(str(e))
                return
    # --save [NAME]: snapshot the EFFECTIVE query (template + CLI overrides);
    # `scan A --save` updates A, `scan A --save B` derives B from A
    if getattr(args, "save", False):
        target = args.save if isinstance(args.save, str) else getattr(args, "name", None)
        if not target:
            print("--save needs a template name: finresearch scan NAME --save "
                  "(or --save NAME)")
            return
        existing_names = set(load_scans())
        p = save_scan(target, args)
        scans = load_scans()  # sanity: written file still parses
        if target not in scans:
            print(f"WARNING: wrote {p} but template '{target}' did not parse back")
            return
        used = {k: v for k, v in scans[target].items() if k != "description"}
        verb = "Replaced" if target in existing_names else "Saved"
        print(f"{verb} scan '{target}' -> {p}")
        print(f"  config: {used or '(all defaults: add at least one filter)'}")
        print(f"  run it: finresearch scan {target}")
        return
    # bare scan (no name, no flags): list saved templates / show how to start;
    # flags without a name run a one-off query
    if not getattr(args, "name", None) and not has_query(args):
        if list_scans():
            return
        print("No saved scan templates yet. Start one:")
        print("  finresearch scan myscan1 --price 5 100 --avgvol-min 500000 "
              "--save --desc 'my value scan'")
        print("then run it by name: finresearch scan myscan1")
        print("or run one-off filters directly: finresearch scan --region jp --pe-max 10")
        return
    try:
        total, quotes = run_scan(args)
    except ValueError as e:
        print(str(e))
        return
    except Exception as e:
        print(f"scan failed: {e}")
        return
    quotes, dropped = post_filter(quotes, args)
    if args.json:
        print(json.dumps({"total": total, "dropped_by_post_filter": dropped,
                          "results": quotes}, indent=2, default=str))
        return
    print(f"=== market scan — region {args.region}"
          + (f", sector~{args.sector}" if args.sector else "")
          + (f", industry~{args.industry}" if args.industry else "")
          + " ===\n")
    rows = [_row_from_quote(qt) for qt in quotes[:args.limit]]
    print_table(["symbol", "name", "price", "day %", "mktcap", "volume", "P/E", "P/B"], rows)
    note = f"showing {len(rows)} of {total} total matches"
    if dropped:
        note += f" ({dropped} dropped by 52w post-filters)"
    if total is not None:
        print(f"\n{note} "
              "(raise --limit up to 250; Yahoo delayed unofficial data)")


def register(subparsers):
    scan = subparsers.add_parser(
        "scan", help="Full-market screen: filter ALL stocks server-side (Yahoo engine)")
    scan.add_argument("name", nargs="?", default=None,
                      help="Run a saved scan template from ~/.config/finresearch/scans.toml "
                           "(bare 'scan' lists saved templates)")
    scan.add_argument("--save", nargs="?", const=True, default=False, metavar="NAME",
                      help="Save the effective query as a template: under the run "
                           "template's name, or under NAME (scan A --save B derives B)")
    scan.add_argument("--desc", default=None, help="Description stored with --save")
    scan.add_argument("--region", default="us",
                      help="Yahoo region code (us, jp, gb, de... default: us)")
    for name, (field, unit) in FIELD_MAP.items():
        if unit == "price":
            scan.add_argument(f"--{name}", nargs=2, type=float, metavar=("LO", "HI"),
                              help=f"{name} range (raw numbers)")
        else:
            scan.add_argument(f"--{name}{MIN_SUFFIX}", type=float,
                              help=f"min {name} (percent-units field: enter %% number)")
            scan.add_argument(f"--{name}{MAX_SUFFIX}", type=float, help=f"max {name}")
    scan.add_argument("--sector", default=None,
                      help="Sector (fuzzy: 'financial', 'tech'...)")
    scan.add_argument("--industry", default=None,
                      help="Industry (fuzzy against Yahoo's list)")
    scan.add_argument("--sort", choices=sorted(SORT_MAP), default="mktcap",
                      help="Sort field (default: mktcap)")
    scan.add_argument("--ascending", action="store_true",
                      help="Ascending sort (default: descending)")
    scan.add_argument("--limit", type=int, default=20,
                      help="Max results, 250 page cap (default: 20)")
    scan.add_argument("--within-high", type=float, default=None, metavar="FRACTION",
                      help="Keep rows within this fraction of the 52w high "
                           "(0.25 = within 25%%; client-side, use with --limit 250)")
    scan.add_argument("--below-high", type=float, default=None, metavar="FRACTION",
                      help="Keep rows AT LEAST this far below the 52w high "
                           "(0.2 = down 20%%+; client-side)")
    scan.add_argument("--off-low", type=float, default=None, metavar="FRACTION",
                      help="Keep rows at least this fraction above the 52w low "
                           "(0.3 = 30%%+ off the low; client-side)")
    scan.add_argument("--json", action="store_true", help="Output as JSON")
    # capture every parser default once — the template layer uses these to
    # distinguish "CLI explicitly set" from "still at default"
    SCAN_DEFAULTS.clear()
    for action in scan._actions:
        if action.dest not in ("help", "name", "save", "desc", "json"):
            SCAN_DEFAULTS[action.dest] = action.default
