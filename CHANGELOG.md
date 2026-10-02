# Changelog

All notable changes to finresearch. Format follows
[Keep a Changelog](https://keepachangelog.com); versions are semver.

## [1.1.1] — 2026-10-02

Documentation release for agents and Japanese users: an Agent Skills guide
to the whole tool, a reorganized AGENTS.md, and Japanese README/CHANGELOG.
No behaviour changes.

### Added
- `skills/finresearch/SKILL.md`: an Agent Skills guide that teaches an agent the
  whole tool — which command answers which question, workflows, units and data
  caveats, the output contract. Linked as a project skill at
  `.claude/skills/finresearch`; `scripts/install-agent-files.sh` creates the link.
- Japanese documentation: `README.ja.md` and `CHANGELOG.ja.md`.
- `tests/test_docs.py`: every command must appear in the skill and in
  `docs/JSON.md`, and the Japanese changelog must list every release.

### Docs
- `AGENTS.md` reorganized into Part A (agents using the tool: calling contract,
  command map, units, etiquette) and Part B (working on the repo), plus a
  release process (every version gets a GitHub Release).
- Corrected counts in README and the 1.0.0 entry: 54 FRED aliases (was "56"),
  24 `scan` filter fields (was "~90"), 59 Yahoo regions (was "58"); added
  `beta`, `pb`, and `perf-52w` to the README's scan field table.

## [1.1.0] — 2026-10-02

Full machine-readable output: every command now speaks JSON, and every command
follows one output contract — built for AI agents, scripts, and cron jobs.

### Added
- `--json` on the last ten commands without it: `sec` (key facts, `--type`,
  `--concept` with full history), `compare`, `transcript`, `fred dashboard`,
  `fred list`, `fred yield_curve`, `fomc calendar`, `fomc sentiment`, `13f who`,
  `13f diff`. Every command now takes `--json`.
- `gappers --json` (alias of `--format json`), so one flag works everywhere.
- `scan --json` lists saved templates; `scan NAME --save --json` reports what was saved.
- `docs/JSON.md`: the output contract plus every command's JSON shape and units.
- `FINRESEARCH_DEBUG=1` shows the full traceback instead of the one-line error.

### Changed
- One output contract for all commands: exit `0` on success (empty results are
  valid JSON, not errors), exit `1` with a single `finresearch: error: …` line on
  stderr for errors, exit `2` for usage errors (including a command family run
  without its subcommand, which used to exit 1). Unexpected exceptions become
  that one line too, with credentials masked.
- Errors that used to print to stdout and exit 0 now exit 1 on stderr: unknown
  tickers (`ticker`, `sec`, `insider detail`, `news`, `13f holder`), unknown
  scan templates and sectors, a failed scan, an unreachable SEC FTD archive, and
  a filer without a 13F holdings table.
- Unknown tickers: `ticker` errors instead of printing a table of N/A;
  `compare`/`screen` report them as per-ticker `error` entries; `insider scan`,
  `activist`, `dilution`, `buyback`, and `8k` skip them with a `[skip]` notice on
  stderr. Each fails only when no ticker yields data.
- `fred series --json` observation values are numbers (were strings).
- `13f holder --json` adds `holder` and `cik`; `screen --json` no longer
  leaks internal fields into `query.filters`.

### Fixed
- `13f holder --json` printed its "Fetching…" progress line to stdout, breaking
  JSON parsing; it goes to stderr now.
- `gappers --json` could emit source-failure notices to stdout; they go to stderr.
- `news` accepted unknown tickers (Google Finance answers them with a generic
  200 page) and its company name and price parsing had broken after a markup
  change; quotes are now validated by page title, names come from the title, and
  the price is read from the quote's own "Current" field (ETF pages: `null`).

### Docs
- README: "Built for agents and automation" — the machine contract, tool-calling
  and cron recipes, jq pipelines, and rate etiquette for unattended runs.
- Corrected which settings can come from a `.env` file (`FRED_API_KEY` only;
  `FINRA_API_KEY` and `FINRESEARCH_SEC_UA` are environment-only).

## [1.0.0] — 2026-10-02

First public release. A free, portable, no-broker-lock-in financial research
CLI built and battle-tested over months of daily use.

### Features
- **Market data** (`ticker`, `compare`, `technicals`, `screen`): fundamentals,
  analyst estimates, holders, RSI/MACD/Bollinger/MAs — currency aware: prices in
  the listing currency, fundamentals in the reporting currency (JP tickers
  render in ¥; ADRs like TSM show USD prices and TWD financials).
- **Full-market scanning** (`scan`): server-side filtering of the entire
  market across 24 filter fields via Yahoo's screener engine — price/mktcap ranges,
  volume, margins, growth, ROE, short interest, institutional/insider %,
  dividends, debt, Altman Z, beta, P/B, 52w performance; 59 regions
  (`jp` native); named scan templates (`scan myscan`) saved in
  `~/.config/finresearch/scans.toml`; 52w-extreme post-filters
  (`--within-high/--below-high/--off-low`).
- **SEC EDGAR suite** (`insider`, `13f`, `13f diff`, `activist`, `dilution`,
  `buyback`, `8k`, `ftd`, `sec`): Form 4 insider scans, institutional 13F
  holdings and quarter-over-quarter holder diffs, activist 13D/G stakes,
  S-3/424B dilution events, XBRL repurchase spend, 8-K event streams,
  official Fails-to-Deliver aggregates.
- **Derivatives & positioning** (`options`, `short`): unusual options activity
  (volume/OI, P/C, IV skew), FINRA consolidated short interest by
  days-to-cover.
- **Macro** (`fred`, `fomc`): FRED dashboard/yield-curve, FOMC statements,
  minutes, hawk/dove sentiment diffs, meeting calendar, and market-implied
  rate odds via Polymarket.
- **News & premarket** (`news`, `gappers`): Google Finance headlines, premarket
  gap scanner with TV/StockAnalysis data.
- **Agent-first** (`AGENTS.md` + `scripts/install-agent-files.sh`): project
  guidance read natively by Codex/Grok/pi/Hermes, CLAUDE.md symlink for Claude
  Code; `scripts/privacy-sweep.sh` for release hygiene with repo-external
  token config.
- **Ready-made strategies** (`examples/`): seven scan templates adapted from
  well-known public methodologies (momentum breakouts, trend template,
  CAN SLIM proxy, quality-dip, daily movers, volume, JP quality), each
  annotated with what a server-side screener cannot express.

### Design commitments
- Free and official data sources only; optional keys (`FRED_API_KEY`,
  `FINRA_API_KEY`) never required for core operation.
- All user state lives outside the repo under `~/.config/finresearch/`
  (downloaded reference data and saved scan output under `~/.cache/finresearch/`).
- Polite by construction: one paced fetcher for every SEC request, FRED
  fetches only the observations it shows, 8-K item codes come from the
  submissions feed rather than per-filing downloads.
- 117-test offline suite, ruff policy, gitleaks secret scan, and CI on Python
  3.10/3.12 (tests + ruff + gitleaks on every push/PR).