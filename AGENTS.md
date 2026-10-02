# AGENTS.md — finresearch

Guidance for AI agents. Codex, Grok, pi, and Hermes read this file; Claude Code
reads `CLAUDE.md`, a symlink to it. Humans: start with `README.md`
([日本語](README.ja.md)).

This file serves two audiences:

- **Part A — Using finresearch.** You are an agent that calls the CLI to answer
  financial-research questions.
- **Part B — Working on finresearch.** You are a coding agent changing this
  repository.

The complete usage guide is the skill at
[`skills/finresearch/SKILL.md`](skills/finresearch/SKILL.md). Claude Code in
this repo loads it automatically via `.claude/skills/finresearch`. Every
command's JSON shape is in [`docs/JSON.md`](docs/JSON.md).

---

# Part A — Using finresearch

## What it is

A free CLI over official public data: SEC EDGAR (insider Form 4, 13F, 13D/G,
S-3/424B, buybacks, 8-K, fails-to-deliver), FINRA short interest, FRED macro,
Federal Reserve FOMC documents, Polymarket FOMC odds, and Yahoo Finance
(fundamentals, technicals, options, full-market screening, US and Japanese
listings). It is built to be driven by agents and cron jobs.

## The calling contract

```bash
finresearch <command> [args] --json      # every command takes --json
```

| Exit | stdout | stderr | Meaning |
|---|---|---|---|
| `0` | exactly one JSON document | diagnostics, `[skip]` notices | success; empty JSON (`[]`, `"rows": []`) = nothing found, not an error |
| `1` | empty | one line `finresearch: error: …` | error: unknown ticker, no data, source unreachable, bad template |
| `2` | empty | argparse usage | bad flag / missing argument / family without subcommand |

- Never prompts; safe under cron and tool-calling harnesses.
- `FINRESEARCH_DEBUG=1` prints a traceback instead of the one-line error.
- No API keys are needed except `FRED_API_KEY` (free) for `fred`.
  `FINRA_API_KEY` (optional) gives current short interest.
  `FINRESEARCH_SEC_UA="tool/1.0 you@domain"` is recommended for heavy SEC use.
- `FINRESEARCH_CONFIG_DIR` points a job at its own `watchlist.txt`,
  `scans.toml`, and `.env`.

## Command map

| Question | Command |
|---|---|
| Company snapshot / statements / estimates / earnings / holders / technicals | `ticker SYM [--section overview\|financials\|kpis\|earnings\|insiders\|holdings\|technicals\|all]` |
| Several companies side by side | `compare A B C` |
| SEC XBRL facts, one metric's history, filings by form | `sec SYM`, `sec SYM --concept revenue`, `sec SYM --type 10-K` |
| Insider open-market buys/sells; every Form 4 | `insider scan [--tickers A,B] [--days N] [--min-value $]`, `insider detail SYM [--days N]` |
| A fund's holdings; who holds / added / exited an issuer | `13f holder FILER`, `13f who ISSUER NAME`, `13f diff ISSUER NAME` |
| Activist stakes, dilution, buybacks, 8-K events | `activist A,B`, `dilution A,B`, `buyback A,B`, `8k A,B [--has 4.01,4.02]` |
| Fails-to-deliver, short interest, options flow | `ftd top`, `ftd sym SYM`, `short`, `options SYM` |
| Whole-market screen; filter a list; saved screens | `scan [filters] [--region jp]`, `screen --tickers A,B [filters]`, `scan NAME` |
| Premarket movers; headlines; transcript links | `gappers`, `news SYM`, `transcript SYM` |
| Macro | `fred dashboard`, `fred yield_curve`, `fred series ALIAS\|ID`, `fred search Q`, `fred list` |
| Fed | `fomc calendar`, `fomc statement [DATE]`, `fomc minutes [DATE]`, `fomc sentiment`, `fomc odds` |

## Read the numbers correctly

- **Fractions vs percent points**: ratios are fractions (`0.276` = 27.6%);
  keys ending `_pct` are percent points. Exceptions that are percent points:
  `ticker` `dividend_yield` and `scan` `regularMarketChangePercent`.
- **`scan` filters take percent numbers** (`--netmargin-min 20` = 20%), while
  the 52w filters `--within-high/--below-high/--off-low` take fractions (0.25).
- **Currencies**: `currency` = listing (price, market cap, EPS, targets),
  `financial_currency` = reporting (revenue, EBITDA, FCF, statements). They
  differ for ADRs. Japanese listings (`7203.T`) are JPY; `scan --region jp`
  market caps are in yen (`5e12` = ¥5T). SEC-derived values are USD.
- **Staleness**: 13F = quarter-end, filed up to 45 days later; keyless `short`
  = FINRA's frozen historical slice (check `mode`); FTD = twice monthly.
- **US-only**: SEC, 13F, insider, FINRA, FTD, and options data.
- Form 4 `shares`/`price` are as-filed strings; `fomc` sentiment is a keyword
  heuristic; data is research input, not investment advice.

## Etiquette

One command at a time. Keep SEC back-scans (`insider`, `13f`, `8k` `--days`)
modest. Don't loop Yahoo-backed commands (`ticker`, `compare`, `screen`,
`scan`, `options`). A full `fred dashboard` costs about 40 of FRED's 120
requests per minute.

---

# Part B — Working on finresearch

## Project principles

finresearch is a free, open-source financial-research CLI (MIT, Python ≥3.10).

- **Portable**: no paid APIs, no broker lock-in, no single-user config. All
  user-specific files live OUTSIDE the repo under `~/.config/finresearch/`
  (watchlist, `.env`, `scans.toml`). Never re-introduce personal defaults, real
  emails, or watchlists into source files.
- **Free + official first**: SEC EDGAR (declared UA, polite pacing), FRED,
  FINRA, and Polymarket are native; yfinance/TradingView/Google Finance are
  unofficial and flagged as such in the README. Don't add sources that need
  paid keys.
- **Agent-first output**: every command honours the output contract (Part A,
  enforced by tests).
- **Every claims-bearing module is live-verified before commit** (see "Unit
  contracts"). Never merge a data-module change that hasn't run against the
  real endpoint.

## Setup

```bash
python -m venv .venv                                    # fresh clone only
uv pip install --python .venv/bin/python -e ".[dev]"   # the venv has no pip; use uv
.venv/bin/finresearch --version                         # smoke check
./scripts/install-agent-files.sh                        # CLAUDE.md, project skill, .cursor rule
```

- Python ≥3.10 enforced in `pyproject.toml`; `tomllib` is stdlib on 3.11+, and
  the template loader degrades gracefully on 3.10 (`tomli` in `[dev]`).
- Never install into the system Python; the repo runs from `.venv/`.
- Data keys (`FRED_API_KEY`, `FINRA_API_KEY`) are OPTIONAL and never belong in
  the repo; modules must work keyless.

## Verify gates (run before every commit)

```bash
.venv/bin/python -m pytest tests/ -q          # 140 tests, ~1s — must be 100%
.venv/bin/python -m ruff check src/ tests/    # must be: All checks passed!
gitleaks git -v .                             # must be: no leaks found
./scripts/privacy-sweep.sh                    # must print: SWEEP CLEAN (or SKIP w/o config)
./scripts/privacy-sweep.sh --history          # same, over every commit + commit/tag metadata
```

CI (`.github/workflows/ci.yml`, Python 3.10 + 3.12) runs the first three on
every push/PR. The privacy sweep is local-only: its tokens live OUTSIDE the
repo in `~/.config/finresearch/sweep-tokens.txt` (never committed), and it sees
local refs only. After any history rewrite, recreate the remote repository;
GitHub keeps force-pushed-over commits reachable by SHA.

## Repository map

```
src/finresearch/
├── cli.py              # argparse wiring ONLY: build_parser(), LAZY dispatch table (COMMANDS),
│                       # top-level handler (uncaught exception -> one stderr line, exit 1)
├── output.py           # THE output contract: emit_json (stdout), warn (stderr), fail (exit 1), redact
├── config.py           # config dir, watchlist, cache dir, versioned User-Agent
├── formatting.py       # fmt_num(val, unit) — unit-aware ($, ¥, X/shares, shares); TIER ORDER: T, B, M
│                       # fmt_pct: FRACTION by default, percent_units=True; print_table lives HERE
├── yfinance_cmd.py     # ticker/compare: INFO_SECTIONS/COMPARE_FIELDS drive JSON + markdown
├── technicals.py       # RSI/MACD/Bollinger/MAs on 1y history (200d falls back to info)
├── screener.py         # screen: ticker LIST filter, not market-wide
├── market_scan.py      # scan: Yahoo SERVER-SIDE screener + templates (scans.toml)
├── sec_edgar.py        # sec command; find_cik / resolve_cik / resolve_ciks (skip + fail-if-none)
├── edgar_common.py     # THE ONE paced EDGAR fetcher (_get), list_filings (+8-K items),
│                       # cached filing_index, doc fetch, namespace-agnostic XML helpers
├── insiders.py         # Form 4      ├── form13f.py (holder/who, value-scale detection)
├── form13f_diff.py     # 13f diff    ├── activist.py (SC 13D/G)   ├── dilution.py (S-3/424B)
├── buyback.py          # XBRL spend  ├── events8k.py (8-K items)  ├── ftd.py / short_interest.py
├── fomc.py             # calendar/statement/minutes/sentiment (whole-word term scoring)
├── fomc_odds.py        # Polymarket odds (registered as a fomc SUBCOMMAND)
├── fred.py             # aliases (+pc1 transforms), series/dashboard/yield_curve/search/list
├── options_flow.py     # option chains → P/C, IV skew, vol/OI
├── news.py             # Google Finance quote pages (shared with gappers catalysts)
├── premarket_gappers.py# TradingView / StockAnalysis SSR scrape
└── transcript.py       # transcript links (no redistribution)
docs/JSON.md            # JSON shapes + output contract (skills/finresearch/references/JSON.md links here)
skills/finresearch/     # SKILL.md: the agent usage guide (Agent Skills format)
tests/                  # offline unit tests; test_json_contract.py guards the output contract
scripts/                # install-agent-files.sh, privacy-sweep.sh
examples/               # scans.toml templates + README
README.md / README.ja.md, CHANGELOG.md / CHANGELOG.ja.md   # keep both languages in sync
```

## Adding or changing a command

1. Module with `cmd_x(args)` (+ optional `register(subparsers)` for families
   like `fomc odds`/`scan`); add its parser and a `COMMANDS` entry in `cli.py`.
2. **Output contract** (enforced by `tests/test_json_contract.py`): the command
   takes `--json`; JSON mode writes exactly one document via
   `output.emit_json` with raw numbers and `null` for missing. Diagnostics go
   through `output.warn`. Errors call `output.fail`. Never `print` an error to
   stdout or exit 0 on failure. "Nothing found" is empty JSON, not an error.
3. EDGAR HTTP goes through `edgar_common._get` (never a private fetcher);
   tables use `formatting.print_table`; percents use `fmt_pct` with explicit units.
4. Tests in `tests/` (no network); live-verify against the real endpoint.
5. Docs: `docs/JSON.md` (shape), `skills/finresearch/SKILL.md` (when/how to
   use it), `README.md` **and** `README.ja.md`, and `CHANGELOG.md` **and**
   `CHANGELOG.ja.md`. `tests/test_docs.py` fails if a command is missing from
   the skill or the JSON reference.

## Unit contracts (verified live — DO NOT break silently)

These were pinned empirically against real endpoints; changing them requires
re-verification:

- **Yahoo scan ratios are PERCENT-coded**: `netincomemargin`, `grossmargin`,
  `divyield`, `shortfloat`, `inst-held`, `day-chg`, `perf-52w` filters take
  percent numbers (20 = 20%). `pe`, `beta`, `pb`, `dtc`, volumes are raw.
  Verify via the `total` echo, not page rows (`count` is page-size-capped).
- **Yahoo's server-side 52w query fields are absolute PRICES**: distance-from-
  high/low cannot be expressed server-side; `--within-high/--below-high/--off-low`
  are CLIENT-side post-filters on the fetched page (fractions: 0.25 = 25%).
- **yfinance 1.4.x delivers `dividendYield` in PERCENT points** (a fraction in
  older versions); screener stores a fraction, display uses
  `fmt_pct(percent_units=True)`. So is the screener quote field
  `regularMarketChangePercent`. Everything else ratio-like from `info`
  (margins, ROE, payout, growth, `shortPercentOfFloat`, holder `pctHeld`) is a
  FRACTION; `fmt_pct` never guesses units from magnitude.
- **Unknown Yahoo symbols** return a near-empty `info` without `quoteType`;
  treat that as "no quote" (`yfinance_cmd._has_quote`).
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
  honour 10 req/s; archives on `www.sec.gov`, data APIs on `data.sec.gov`.
- **EDGAR submissions feed** carries 8-K item codes in its `items` column, so
  there's no need to fetch documents to learn them.
- **FINRA CSV**: `issueName` may contain UNQUOTED commas, so parse right-anchored
  (last 11 fields fixed); `daysToCoverQuantity` 999.99 = missing-ADV sentinel.
- **SEC FTD zips**: one pipe-delimited latin-1 file, 6 fields, `.` price =
  none; two trailer lines (`record count N`, `total quantity of shares N`);
  a record-count mismatch warns on stderr.
- **FRED**: `units=pc1` gives % change from a year ago server-side (the `*_yoy`
  aliases); `sort_order=desc&limit=N` fetches only the newest points. The API key
  travels in the query string, so error text always goes through `output.redact`.
- **Google Finance** answers unknown symbols with a generic 200 page: a real
  quote's `<title>` contains `(TICKER)`; the quote price sits behind the
  "Current" label (other price spans belong to the ticker bar; ETFs have none).
- **Polymarket gamma**: outcomePrices/outcomes are JSON-encoded STRINGS, so
  json.loads them; `/search` params are silently ignored, use `public-search`;
  normalize Yes-price sums across negRisk buckets.
- **`fmt_num` tier order**: T (1e12) → B → M; check TRILLION before BILLION.

## Conventions

- Tests: pytest, no network in unit tests. Live verification is done manually
  before commit, not in CI; CI must stay fast and keyless.
- Commit style: `feat:|fix:|docs:|refactor:|test:` one-line subjects. Commit
  and tag timestamps in UTC (`TZ=UTC`, `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`).
- CHANGELOG.md **and** CHANGELOG.ja.md are updated for every user-visible
  change; README.md and README.ja.md change together.

## Release process

1. Bump `version` in `pyproject.toml` and `__version__` in
   `src/finresearch/__init__.py` (semver: features → minor, fixes → patch);
   `uv lock`; reinstall; `finresearch --version`.
2. Move the `[Unreleased]` notes into a dated `[X.Y.Z]` section in
   `CHANGELOG.md` and `CHANGELOG.ja.md`.
3. Run all verify gates and live-verify the changed commands.
4. Commit, then an annotated tag `vX.Y.Z` (UTC); push `main` and the tag.
5. Create the GitHub Release from the CHANGELOG section:
   `gh release create vX.Y.Z --title "finresearch vX.Y.Z" --notes-file <notes>`.
   Every version gets a release page.

## Known weak spots

- `quality-dip`-style scans depend on client-side post-filters interacting with
  the 250-row page cap (see examples/README.md).
- `insider`/`13f` modules are rate-limit-sensitive on large back-scans; keep
  `--days` modest.
- `13f diff` compares a filer's largest matching row, which can be an option
  position when that's all the filer holds.
- The screener engine (`scan`) shares Yahoo's rate sensitivity; don't loop it.
- Scrapers (`news`, `gappers`) depend on third-party page markup and break
  when it changes; their tests pin the parsing rules.
