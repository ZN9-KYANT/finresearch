"""FRED (Federal Reserve Economic Data) commands.

Fetches macroeconomic indicators from the St. Louis Fed FRED API.
Free API key required: https://fred.stlouisfed.org/docs/api/api_key.html
(`fred list` works without one).
"""

import json as json_module
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

from .config import DEFAULT_USER_AGENT, config_dir
from .output import emit_json, redact

FRED_BASE = "https://api.stlouisfed.org/fred"

# Curated series aliases — friendly names → FRED series IDs
SERIES_ALIASES = {
    # Interest rates
    "fed_funds": "FEDFUNDS",
    "fed_funds_rate": "FEDFUNDS",
    "effr": "DFF",            # Effective Federal Funds Rate (daily)
    "sofr": "SOFR",            # Secured Overnight Financing Rate
    "prime": "DPRIME",         # Prime rate
    "mortgage_30": "MORTGAGE30US",
    "mortgage_15": "MORTGAGE15US",
    # Treasury yields
    "treasury_2y": "DGS2",
    "treasury_10y": "DGS10",
    "treasury_30y": "DGS30",
    "treasury_3m": "DGS3MO",
    "treasury_6m": "DGS6MO",
    "treasury_1y": "DGS1",
    "treasury_5y": "DGS5",
    "treasury_7y": "DGS7",
    "treasury_20y": "DGS20",
    # Yield curve spreads
    "spread_2y_10y": "T10Y2Y",    # 10Y-2Y spread (recession indicator)
    "spread_3m_10y": "T10Y3M",    # 10Y-3M spread
    # Inflation
    "cpi": "CPIAUCSL",            # CPI All Urban Consumers (headline)
    "cpi_core": "CPILFESL",       # Core CPI (ex food & energy)
    "cpi_yoy": "CPIAUCSL",        # headline CPI, % change from a year ago (see TRANSFORMS)
    "pce": "PCEPI",               # PCE Price Index
    "pce_core": "PCEPILFE",       # Core PCE price index (ex food & energy)
    "pce_yoy": "PCEPILFE",        # Core PCE, % change from a year ago (Fed's preferred)
    "breakeven_10y": "T10YIE",     # 10Y inflation breakeven
    "breakeven_5y": "T5YIE",
    # Employment
    "unemployment": "UNRATE",
    "unemployment_rate": "UNRATE",
    "nonfarm_payrolls": "PAYEMS",
    "initial_claims": "ICSA",      # Initial jobless claims
    "continuing_claims": "CCSA",
    "labor_force": "CLF16OV",
    "participation": "CIVPART",    # Labor force participation rate
    # GDP & growth
    "gdp": "GDP",
    "gdp_growth": "A191RL1Q225SBEA",  # Real GDP growth rate (quarterly, SAAR)
    "potential_gdp": "GDPPOT",
    # Money supply
    "m2": "M2SL",
    "m2_yoy": "M2SL",              # M2, % change from a year ago
    # Consumer
    "consumer_credit": "TOTALSL",
    "retail_sales": "RSAFS",
    "personal_savings": "PSAVERT",  # Personal savings rate
    "disposable_income": "DSPIC96",
    # Business
    "industrial_production": "INDPRO",
    "capacity_utilization": "TCU",
    "housing_starts": "HOUST",
    "building_permits": "PERMIT",
    "new_home_sales": "HSN1F",
    "existing_home_sales": "EXHOSLUSM495S",  # NAR; FRED keeps a rolling window
    "case_shiller": "CSUSHPISA",    # S&P Case-Shiller Home Price Index
    # Market
    "vix": "VIXCLS",
    "sp500": "SP500",
    "dollar_index": "DTWEXBGS",    # Trade-weighted dollar index
    # Fed balance sheet
    "fed_balance_sheet": "WALCL",  # Total assets of all Federal Reserve Banks
    # Recession indicator
    "recession_prob": "RECPROUSM156N",  # Smoothed recession probability
}

# Aliases served through a FRED units transformation (pc1 = % change from a
# year ago, computed by FRED itself) instead of the raw level
TRANSFORMS = {
    "cpi_yoy": "pc1",
    "pce_yoy": "pc1",
    "m2_yoy": "pc1",
}
_TRANSFORM_UNITS = {"pc1": "Percent Change from Year Ago"}

# Quick-access indicator groups for the dashboard
DASHBOARD_GROUPS = {
    "rates": ["DFF", "FEDFUNDS", "DGS2", "DGS10", "DGS30", "T10Y2Y"],
    "inflation": ["CPIAUCSL", "CPILFESL", "PCEPILFE", "T10YIE"],
    "employment": ["UNRATE", "PAYEMS", "ICSA", "CIVPART"],
    "growth": ["GDP", "A191RL1Q225SBEA"],
    "money": ["M2SL", "WALCL"],
    "housing": ["HOUST", "PERMIT", "CSUSHPISA"],
    "market": ["VIXCLS", "DTWEXBGS"],
}

HEADERS = {"User-Agent": DEFAULT_USER_AGENT}

# requests puts the full URL (api_key included) in its error text
_redact = redact


def _get_api_key():
    """FRED API key from env, else FRED_API_KEY= in ~/.config/finresearch/.env or ./.env."""
    key = os.getenv("FRED_API_KEY")
    if key:
        return key
    for env_path in (config_dir() / ".env", os.path.join(os.getcwd(), ".env")):
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("FRED_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip("'\"")
                        if key:
                            return key
        except OSError:
            continue
    print("Error: FRED_API_KEY not set in environment.", file=sys.stderr)
    print("Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html", file=sys.stderr)
    sys.exit(1)


def _resolve_series(name):
    """Resolve a friendly alias or return the raw series ID."""
    key = name.lower().strip()
    if key in SERIES_ALIASES:
        return SERIES_ALIASES[key]
    # If not an alias, treat as raw FRED series ID (uppercase)
    return name.upper()


def _resolve_transform(name):
    """FRED units transformation for an alias (e.g. 'pc1'), or None."""
    return TRANSFORMS.get(name.lower().strip())


def _fetch_series(series_id, api_key=None, observation_start=None, observation_end=None,
                  limit=None, transform=None):
    """Observations (oldest first) for one FRED series.

    limit: only the newest N observations (FRED sorts desc server-side), so the
    dashboard/yield curve never download decades of daily history.
    transform: FRED `units` transformation, e.g. 'pc1' (% change from year ago).
    """
    api_key = api_key or _get_api_key()
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }
    if observation_start:
        params["observation_start"] = observation_start
    if observation_end:
        params["observation_end"] = observation_end
    if limit:
        params.update(sort_order="desc", limit=limit)
    if transform:
        params["units"] = transform

    url = f"{FRED_BASE}/series/observations"
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 429:
            print(f"  [warn] FRED rate limited for {series_id}", file=sys.stderr)
            return None
        if resp.status_code != 200:
            print(f"  [warn] FRED error {resp.status_code} for {series_id}", file=sys.stderr)
            return None
        data = resp.json()
        observations = data.get("observations", [])
        if limit:
            observations.reverse()
        # Filter out missing values (".")
        valid = [o for o in observations if o.get("value", ".") != "."]
        info = _fetch_series_info(series_id, api_key)
        return {
            "series_id": series_id,
            "title": info["title"],
            "observations": valid,
            "units": _TRANSFORM_UNITS.get(transform) or info["units"],
            "frequency": info["frequency"],
        }
    except requests.RequestException as e:
        print(f"  [warn] FRED request failed for {series_id}: {_redact(e)}", file=sys.stderr)
        return None


_SERIES_INFO = {}  # series_id -> info; successes only, so a 429 is retried later


def _fetch_series_info(series_id, api_key):
    """Fetch series title and units from FRED (successful lookups cached per run)."""
    if series_id in _SERIES_INFO:
        return _SERIES_INFO[series_id]
    url = f"{FRED_BASE}/series"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            s = data.get("seriess", [{}])[0]
            _SERIES_INFO[series_id] = {
                "title": s.get("title", series_id),
                "units": s.get("units", ""),
                "frequency": s.get("frequency", ""),
                "seasonal_adjustment": s.get("seasonal_adjustment_short", ""),
                "popularity": s.get("popularity", ""),
            }
            return _SERIES_INFO[series_id]
    except (requests.RequestException, IndexError, KeyError):
        pass
    return {"title": series_id, "units": "", "frequency": "", "seasonal_adjustment": "", "popularity": ""}


def _fetch_latest_many(series_ids, api_key, n=10):
    """Newest n observations for several series, fetched concurrently (order kept)."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda sid: _fetch_series(sid, api_key, limit=n), series_ids))


def _format_value(value_str, units=""):
    """Format a value string with optional units."""
    try:
        val = float(value_str)
        if units.lower().startswith("percent"):
            return f"{val:.2f}%"
        elif units in ("Billions of Dollars", "bil."):
            return f"${val:,.1f}B"
        elif units in ("Millions of Dollars", "mil."):
            return f"${val:,.1f}M"
        elif units in ("Index", "index"):
            return f"{val:.2f}"
        elif units in ("Billions of Dollars, Billions of Chained 2017 Dollars", "bil. of chained"):
            return f"${val:,.1f}B"
        else:
            return f"{val:,.2f}"
    except (ValueError, TypeError):
        return value_str


def _format_trend(observations, n=3):
    """Format a simple trend indicator (last n observations)."""
    if len(observations) < 2:
        return ""
    recent = observations[-n:]
    vals = []
    for o in recent:
        try:
            vals.append(float(o["value"]))
        except (ValueError, TypeError):
            pass
    if len(vals) < 2:
        return ""

    latest = vals[-1]
    prev = vals[-2]
    delta = latest - prev
    pct_change = (delta / prev * 100) if prev != 0 else 0

    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
    return f"{arrow} {abs(pct_change):.1f}% ({abs(delta):.2f})"


def cmd_fred(args):
    """Main FRED command handler."""
    if args.subcommand == "list":
        _cmd_list(args)  # offline: no key needed
        return
    api_key = _get_api_key()
    if args.subcommand == "series":
        _cmd_series(args, api_key)
    elif args.subcommand == "search":
        _cmd_search(args, api_key)
    elif args.subcommand == "yield_curve":
        _cmd_yield_curve(args, api_key)
    else:  # "dashboard", or bare `finresearch fred`
        _cmd_dashboard(args, api_key)


def _cmd_series(args, api_key):
    """Fetch a specific FRED series."""
    series_id = _resolve_series(args.series_name)
    transform = _resolve_transform(args.series_name)

    # Date range
    obs_start = None
    obs_end = None
    if args.days:
        obs_start = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    elif args.years:
        obs_start = (datetime.now() - timedelta(days=args.years * 365)).strftime("%Y-%m-%d")
    if args.start_date:
        obs_start = args.start_date
    if args.end_date:
        obs_end = args.end_date

    # No date range + table output: only the newest rows are shown, so fetch
    # just those (JSON keeps the full history for downstream consumers).
    limit = None
    if not (obs_start or obs_end or args.json):
        limit = max(args.last or 0, 2) + 5  # headroom for '.' (missing) rows
    data = _fetch_series(series_id, api_key, obs_start, obs_end, limit=limit,
                         transform=transform)

    if not data:
        print(f"\n*No data found for series '{series_id}'*", file=sys.stderr)
        sys.exit(1)

    observations = data["observations"]
    title = data["title"]
    units = data.get("units", "")

    if args.json:
        result = {
            "series_id": series_id,
            "title": title,
            "units": units,
            "count": len(observations),
            "observations": [
                {"date": o["date"], "value": _to_float(o["value"])} for o in observations
            ],
        }
        print(json_module.dumps(result, indent=2))
        return

    print(f"\n# {title}")
    print(f"**Series:** {series_id} | **Units:** {units} | **Observations:** {len(observations)}\n")

    if observations:
        latest = observations[-1]
        prev = observations[-2] if len(observations) > 1 else None

        print("## Latest")
        print(f"- **Date:** {latest['date']}")
        print(f"- **Value:** {_format_value(latest['value'], units)}")

        if prev:
            try:
                delta = float(latest["value"]) - float(prev["value"])
                pct = (delta / float(prev["value"]) * 100) if float(prev["value"]) != 0 else 0
                arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
                print(f"- **Change:** {arrow} {abs(delta):.2f} ({abs(pct):.2f}% vs {prev['date']})")
            except (ValueError, TypeError):
                pass

    if args.last and len(observations) > 1:
        print(f"\n## Recent History (last {args.last})\n")
        start = max(0, len(observations) - args.last)
        for o in observations[start:]:
            val = _format_value(o["value"], units)
            print(f"- {o['date']}: {val}")


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _point(series_id, data):
    """Latest observation + change vs the previous one, as JSON-ready numbers."""
    if not (data and data["observations"]):
        return {"series_id": series_id, "available": False}
    obs = data["observations"]
    latest, prev = obs[-1], (obs[-2] if len(obs) > 1 else None)
    val = _to_float(latest["value"])
    pval = _to_float(prev["value"]) if prev else None
    change = round(val - pval, 6) if val is not None and pval is not None else None
    return {
        "series_id": series_id,
        "available": True,
        "title": data["title"],
        "units": data.get("units", ""),
        "frequency": data.get("frequency", ""),
        "date": latest["date"],
        "value": val,
        "prev_date": prev["date"] if prev else None,
        "prev_value": pval,
        "change": change,
        "change_pct": round(change / pval * 100, 4) if change is not None and pval else None,
    }


def _cmd_dashboard(args, api_key):
    """Show a macro dashboard with key indicators."""
    group = getattr(args, "group", None)
    groups = {group: DASHBOARD_GROUPS[group]} if group else DASHBOARD_GROUPS
    fetched = {name: list(zip(sids, _fetch_latest_many(sids, api_key)))
               for name, sids in groups.items()}

    if getattr(args, "json", False):
        emit_json({
            "updated": datetime.now().isoformat(timespec="seconds"),
            "groups": {name: [_point(sid, data) for sid, data in pairs]
                       for name, pairs in fetched.items()},
        })
        return

    print("\n# 📊 FRED Macro Dashboard")
    print(f"*Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

    for group_name, pairs in fetched.items():
        print(f"## {group_name.title()}\n")
        for sid, data in pairs:
            if data and data["observations"]:
                latest = data["observations"][-1]
                trend = _format_trend(data["observations"])
                val = _format_value(latest["value"], data.get("units", ""))
                title_short = data["title"].split("(")[0].strip()[:50]
                print(f"- **{title_short}**: {val} ({latest['date']}) {trend}")
            else:
                print(f"- ~~{sid}~~: *unavailable*")
        print()

    print("---")
    print("*Source: Federal Reserve Economic Data (FRED), St. Louis Fed*")


def _cmd_search(args, api_key):
    """Search for FRED series by keyword."""
    url = f"{FRED_BASE}/series/search"
    params = {
        "search_text": args.query,
        "api_key": api_key,
        "file_type": "json",
        "limit": args.limit,
        "order_by": "popularity",
        "sort_order": "desc",
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"Error: FRED search failed ({resp.status_code})", file=sys.stderr)
            sys.exit(1)
        data = resp.json()
        results = data.get("seriess", [])

        if args.json:
            output = [
                {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "frequency": r.get("frequency"),
                    "units": r.get("units"),
                    "seasonal_adjustment": r.get("seasonal_adjustment"),
                }
                for r in results
            ]
            print(json_module.dumps(output, indent=2))
            return

        print(f"\n# FRED Search: '{args.query}'\n")
        print(f"**{len(results)} series found** (sorted by popularity)\n")

        for r in results:
            sid = r.get("id", "?")
            title = r.get("title", "?")
            freq = r.get("frequency", "?")
            units = r.get("units", "?")
            print(f"- **{sid}**: {title}")
            print(f"  *{freq} • {units}*")

        print("\n---\n*Use: `finresearch fred series <ID>` to fetch data*")

    except requests.RequestException as e:
        print(f"Error: {_redact(e)}", file=sys.stderr)
        sys.exit(1)


# Display grouping for `fred list`
ALIAS_CATEGORIES = {
    "Interest Rates": ["fed_funds", "effr", "sofr", "prime", "mortgage_30", "mortgage_15"],
    "Treasury Yields": ["treasury_3m", "treasury_6m", "treasury_1y", "treasury_2y",
                        "treasury_5y", "treasury_7y", "treasury_10y", "treasury_20y",
                        "treasury_30y"],
    "Yield Spreads": ["spread_2y_10y", "spread_3m_10y"],
    "Inflation": ["cpi", "cpi_core", "cpi_yoy", "pce", "pce_core", "pce_yoy",
                  "breakeven_10y", "breakeven_5y"],
    "Employment": ["unemployment", "nonfarm_payrolls", "initial_claims",
                   "continuing_claims", "labor_force", "participation"],
    "GDP & Growth": ["gdp", "gdp_growth", "potential_gdp"],
    "Money Supply": ["m2", "m2_yoy", "fed_balance_sheet"],
    "Consumer": ["consumer_credit", "retail_sales", "personal_savings",
                 "disposable_income"],
    "Business": ["industrial_production", "capacity_utilization",
                 "housing_starts", "building_permits",
                 "new_home_sales", "existing_home_sales", "case_shiller"],
    "Market": ["vix", "sp500", "dollar_index"],
    "Recession": ["recession_prob"],
}


def _cmd_list(args):
    """List all available aliases (offline)."""
    if getattr(args, "json", False):
        emit_json({
            "aliases": {a: {"series_id": sid, "transform": TRANSFORMS.get(a)}
                        for a, sid in SERIES_ALIASES.items()},
            "categories": ALIAS_CATEGORIES,
        })
        return

    print(f"\n# FRED Series Aliases ({len(SERIES_ALIASES)} available)\n")
    print("Use any alias with: `finresearch fred series <alias>`\n")
    for cat, aliases in ALIAS_CATEGORIES.items():
        print(f"## {cat}\n")
        for a in aliases:
            sid = SERIES_ALIASES.get(a, a.upper())
            note = " (% change from a year ago)" if a in TRANSFORMS else ""
            print(f"- `{a}` → {sid}{note}")
        print()


YIELD_CURVE_TENORS = [
    ("3M", "DGS3MO"), ("6M", "DGS6MO"), ("1Y", "DGS1"), ("2Y", "DGS2"), ("5Y", "DGS5"),
    ("7Y", "DGS7"), ("10Y", "DGS10"), ("20Y", "DGS20"), ("30Y", "DGS30"),
]


def _cmd_yield_curve(args, api_key):
    """Show the current Treasury yield curve."""
    fetched = _fetch_latest_many([sid for _, sid in YIELD_CURVE_TENORS], api_key)
    points = [(label, _point(sid, data))
              for (label, sid), data in zip(YIELD_CURVE_TENORS, fetched)]
    yields = {label: pt["value"] for label, pt in points if pt.get("value") is not None}
    spreads = {name: round(yields[long] - yields[short], 4)
               for name, long, short in (("10Y-2Y", "10Y", "2Y"), ("10Y-3M", "10Y", "3M"))
               if long in yields and short in yields}

    if getattr(args, "json", False):
        emit_json({
            "curve": [{"tenor": label, "series_id": pt["series_id"],
                       "date": pt.get("date"), "yield_pct": pt.get("value")}
                      for label, pt in points],
            "spreads_pct": spreads,
            "inverted": {name: v < 0 for name, v in spreads.items()},
        })
        return

    print("\n# 📈 Treasury Yield Curve\n")
    for label, pt in points:
        if pt.get("value") is not None:
            print(f"- **{label}**: {pt['value']:.3f}% ({pt['date']})")
        else:
            print(f"- {label}: *N/A*")

    if spreads:
        print("\n## Key Spreads")
    for name, spread in spreads.items():
        signal = "⚠️ INVERTED (recession signal)" if spread < 0 else "Normal"
        print(f"- **{name}**: {spread:.3f}% {signal}")

    # Visual curve (ASCII)
    if len(yields) >= 4:
        print("\n## Visual Curve\n```")
        min_y = min(yields.values())
        max_y = max(yields.values())
        for label, val in yields.items():
            bar_len = int((val - min_y) / (max_y - min_y + 0.01) * 40) if max_y > min_y else 20
            bar = "█" * bar_len
            print(f"{label:>4s} │{bar} {val:.2f}%")
        print("```")

    print("\n---\n*Source: FRED, U.S. Treasury daily par yields*")
