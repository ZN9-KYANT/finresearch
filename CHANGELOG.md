# Changelog

All notable changes to finresearch. Format follows
[Keep a Changelog](https://keepachangelog.com); versions are semver.

## [Unreleased]

### Fixed
- `13f holder --json`: the "Fetching latest 13F-HR…" progress line went to stdout
  and broke JSON parsing; it now goes to stderr like every other diagnostic.

### Docs
- README: "Built for agents and automation" — the machine contract (JSON on
  stdout, diagnostics on stderr, non-interactive, keyless, per-job config),
  tool-calling and cron recipes, jq pipelines, and rate etiquette for
  unattended runs. Corrected which settings can come from a `.env` file
  (`FRED_API_KEY` only; `FINRA_API_KEY` and `FINRESEARCH_SEC_UA` are
  environment-only).

## [1.0.0] — 2026-10-02

First public release. A free, portable, no-broker-lock-in financial research
CLI built and battle-tested over months of daily use.

### Features
- **Market data** (`ticker`, `compare`, `technicals`, `screen`): fundamentals,
  analyst estimates, holders, RSI/MACD/Bollinger/MAs — currency aware: prices in
  the listing currency, fundamentals in the reporting currency (JP tickers
  render in ¥; ADRs like TSM show USD prices and TWD financials).
- **Full-market scanning** (`scan`): server-side filtering of the entire
  market across ~90 fields via Yahoo's screener engine — price/mktcap ranges,
  volume, margins, growth, ROE, short interest, institutional/insider %,
  dividends, debt, Altman Z, beta, P/B, 52w performance; 58 regions
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