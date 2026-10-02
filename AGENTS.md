# AGENTS.md — finresearch

Guidance for AI coding agents working in this repository (Codex, Grok, pi,
Hermes read this file; Claude Code reads `CLAUDE.md`, a symlink to it).
Humans: start with `README.md` instead.

## Project overview

finresearch is a free, open-source financial-research CLI (MIT, Python ≥3.10).
Core principles:

- **Portable** — no paid APIs, no broker lock-in, no single-user config. All
  user-specific files live OUTSIDE the repo under `~/.config/finresearch/`
  (watchlist, `.env`, `scans.toml`). Never re-introduce personal defaults, real
  emails, or watchlists into source files.
- **Free + official first** — SEC EDGAR (declared UA, polite pacing), FRED,
  FINRA, Polymarket are native; yfinance/TradingView are unofficial sources and
  flagged as such in README. Don't add sources that need paid keys.
- **Every claims-bearing module is live-verified before commit** — see "Unit
  contracts" below — never merge a data-module change that hasn't run against
  the real endpoint.

## Setup commands

```bash
# repo venv (no pip inside; use uv)
uv pip install --python .venv/bin/python -e ".[dev]"   # after fresh clone: python -m venv .venv first
.venv/bin/finresearch --help                           # smoke check
```

- Python ≥3.10 enforced in `pyproject.toml`; `tomllib` is stdlib on 3.11+ but
  the template loader degrades gracefully on 3.10.
- Never install into the system Python; the repo runs from `.venv/`.
- Data keys (`FRED_API_KEY`, `FINRA_API_KEY`) are OPTIONAL and never belong in
  the repo; modules must work keyless.

## Verify commands (run before every commit)

```bash
.venv/bin/python -m pytest tests/ -q          # 137 tests, ~1s — must be 100%
.venv/bin/python -m ruff check src/ tests/    # must be: All checks passed!
gitleaks git -v .                             # must be: no leaks found
./scripts/privacy-sweep.sh                    # must print: SWEEP CLEAN (or SKIP w/o config)
#   ^ personal-data sweep; tokens live OUTSIDE the repo in
#     ~/.config/finresearch/sweep-tokens.txt (never committed). --history
#     scans every blob in every commit plus commit/tag identities + messages
#     (local refs only: after a history rewrite, recreate the remote repo).
```

All four gates run in CI (`.github/workflows/ci.yml`, py3.10 + 3.12) — the
personal-data sweep is the one CI can't do for you.

## Architecture map

```
src/finresearch/
├── cli.py              # argparse wiring ONLY — parsers + LAZY dispatch table (COMMANDS)
├── config.py           # config dir, watchlist, cache dir, versioned User-Agent
├── output.py           # THE output contract: emit_json (stdout), warn (stderr), fail (exit 1),
│                       # redact; cli.main turns uncaught exceptions into one stderr line
├── formatting.py       # fmt_num(val, unit) — unit-aware ($, ¥, X/shares, shares); TIER ORDER: T, B, M
│                       # fmt_pct: FRACTION by default, percent_units=True for percent points
│                       # print_table lives HERE
├── yfinance_cmd.py     # ticker/compare/financials — listing vs reporting currency (see contracts)
├── technicals.py       # RSI/MACD/Bollinger/MAs (200d falls back to info['twoHundredDayAverage'])
├── screener.py         # watchlist screener (ticker LIST, not market-wide)
├── market_scan.py      # finresearch scan — Yahoo SERVER-SIDE screener engine (see unit contracts)
├── sec_edgar.py        # CIK lookup (find_cik -> (cik, name); resolve_cik -> cik|None)
├── edgar_common.py     # THE ONE paced EDGAR fetcher (_get), list_filings (+8-K items),
│                       # cached filing_index, doc fetch, namespace-agnostic XML helpers
├── insiders.py         # Form 4 parser  ├── form13f.py (holder/who, value-scale detection)
├── form13f_diff.py     # 13f diff      ├── activist.py (SC 13D/G)  ├── dilution.py (S-3/424B)
├── buyback.py          # XBRL spend    ├── events8k.py (8-K items)  ├── ftd.py / short_interest.py
├── fomc.py             # statements/minutes/sentiment + cmd_fomc dispatches subcommands
├── fomc_odds.py        # Polymarket odds (registered as a fomc SUBCOMMAND)
├── options_flow.py     # option chains
├── premarket_gappers.py# TV/StockAnalysis SSR scrape
└── fred.py             # FRED aliases/dashboard
```

New command pattern: module with `cmd_x(args)` (+ optional `register(subparsers)`
for subcommand families like `fomc odds`/`scan`), add the parser and a `COMMANDS`
entry in `cli.py` (imported lazily on dispatch), tests in `tests/`, README +
CHANGELOG entries. `print_table(headers, rows)` comes from `formatting.py`; all
EDGAR HTTP goes through `edgar_common._get` (never a private fetcher).

Output contract (enforced by `tests/test_json_contract.py`): every leaf command
takes `--json`; in JSON mode stdout is exactly one document via
`output.emit_json`, raw numbers, `null` for missing. Diagnostics go through
`output.warn` (stderr). Errors call `output.fail` (stderr line, exit 1) — never
`print` an error to stdout or `return` exit 0 on failure. "Nothing found" is
empty JSON, not an error. Document new shapes in `docs/JSON.md`.

## Unit contracts (verified live — DO NOT break silently)

These were pinned empirically against real endpoints; changing them requires
re-verification:

- **Yahoo scan ratios are PERCENT-coded**: `netincomemargin`, `grossmargin`,
  `divyield`, `shortfloat`, `inst-held`, `day-chg`, `perf-52w` filters take
  percent numbers (20 = 20%). `pe`, `beta`, `pb`, `dtc`, volumes are raw.
  Verify via the `total` echo, not page rows (`count` is page-size-capped).
- **Yahoo's server-side 52w query fields are absolute PRICES** — distance-from-
  high/low cannot be expressed server-side; `--within-high/--below-high/--off-low`
  are CLIENT-side post-filters on the fetched page (fractions: 0.25 = 25%).
- **yfinance 1.4.x delivers `dividendYield` in PERCENT points** (was a
  fraction in older versions); screener stores a fraction, display uses
  `fmt_pct(percent_units=True)`. So is the screener quote field
  `regularMarketChangePercent`. Everything else ratio-like from `info`
  (margins, ROE, payout, growth, `shortPercentOfFloat`, holder `pctHeld`) is a
  FRACTION; `fmt_pct` never guesses units from magnitude.
- **Two currencies**: `info['currency']` (LISTING) covers price, MAs, market cap,
  EPS, targets, and holder values; `info['financialCurrency']` (REPORTING) covers
  revenue, gross profit, EBITDA, FCF, statements, and revenue estimates. Same for
  most listings (JP: both JPY), different for ADRs (TSM: USD vs TWD). Never assume $.
- **13F `<value>` unit**: whole dollars for filings made since 2023-01-03,
  thousands before; non-compliant filers exist, so `detect_value_scale` prices
  the biggest SH row and only falls back to the filing date.
- **EDGAR UA rule**: a UA ending in a non-deliverable email token (e.g.
  `users.noreply.github.com`) gets 403 "Undeclared Automated Tool". Default
  `finresearch/<version> contact@example.com` (`config.py`); `FINRESEARCH_SEC_UA`
  overrides.
- **EDGAR pacing**: 0.25s gap between requests (`edgar_common._get`),
  honor 10 req/s; archives on `www.sec.gov`, data APIs on `data.sec.gov`.
- **FINRA CSV**: `issueName` may contain UNQUOTED commas — parse right-anchored
  (last 11 fields fixed); `daysToCoverQuantity` 999.99 = missing-ADV sentinel.
- **SEC FTD zips**: one pipe-delimited latin-1 file, 6 fields, `.` price =
  none, trailer says `record count N` (checked: a mismatch warns on stderr).
- **EDGAR submissions feed** carries 8-K item codes in its `items` column — no
  need to fetch documents to learn them.
- **FRED**: `units=pc1` gives % change from a year ago server-side (the `*_yoy`
  aliases); `sort_order=desc&limit=N` fetches only the newest points. The API key
  travels in the query string, so never print raw request errors (`fred._redact`).
- **Polymarket gamma**: outcomePrices/outcomes are JSON-encoded STRINGS —
  json.loads them; `/search` params are silently ignored, use `public-search`;
  normalize Yes-price sums across negRisk buckets.
- **`fmt_num` tier order**: T (1e12) → B → M — check TRILLION before BILLION.

## Conventions

- Tests: pytest, no network in unit tests (live verification is done manually
  before commit, not in CI — CI must stay fast and keyless).
- Percent/units: prefer the formatting helpers over ad-hoc f-strings.
- Commit style: `feat:|fix:|docs:|refactor:|test:` one-line subjects.
- CHANGELOG.md is updated for every user-visible change.

## Known weak spots

- `quality-dip`-style scans depend on client-side post-filters interacting with
  the 250-row page cap (see examples/README.md).
- `insider`/`13f` modules are rate-limit-sensitive on large back-scans; keep
  `--days` modest.
- The screener engine (`scan`) shares Yahoo's rate sensitivity; don't loop it.