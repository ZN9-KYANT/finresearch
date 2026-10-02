# finresearch 🌙

[License: MIT](LICENSE) · Python 3.10+ · CI: see `.github/workflows/ci.yml`

**Financial research built for AI agents and research automation.** finresearch is
a free, open-source CLI designed first to be driven by AI agents, cron jobs, and
scripts, and second by people at a terminal. It never prompts, works without API
keys by default, writes JSON to stdout and diagnostics to stderr, and stays polite
to every upstream API when nobody is watching.

It covers fundamentals for US and Japanese listings, SEC EDGAR filings (insider
Form 4, 13F, 13D/G, S-3/424B, buybacks, 8-K), FINRA short interest, SEC
fails-to-deliver, options flow, FRED macro, FOMC statements with market-implied
rate odds, full-market screening, and premarket gappers. Everything comes from
official public sources (SEC EDGAR, FRED, Federal Reserve, FINRA) or free community
endpoints (Yahoo Finance via yfinance). No paid API keys. The open-source
alternative to paid AI financial-data APIs.

→ Jump to [Built for agents and automation](#built-for-agents-and-automation) for the
machine contract, tool-calling and cron recipes.

## Highlights

- **`insider`** — SEC EDGAR-native Form 4 screener: open-market buys and sells with
  insider roles, share counts, prices, and dollar values across your watchlist.
  Parsed from the filings themselves, not a reseller.
- **`13f`** — Institutional holdings from Form 13F-HR: any filer's book
  (`13f holder BRK-B`), which institutions hold a given issuer
  (`13f who NVIDIA CORP`), and quarter-over-quarter holder changes
  (`13f diff NOKIA CORP` — adds, exits, buys, sells per filer), with per-filing
  value-unit detection (a real-world data-quality trap: the unit switched from
  thousands to whole dollars in 2023, and some filers still get it wrong).
- **`activist`** — SC 13D/G ownership stakes on an issuer: who holds 5%+, with
  activist-intent language flagged vs passive 13G holders.
- **`dilution`** — S-3 shelf registrations and 424B priced offerings with share/size
  hints and at-the-market program flags — the bearish mirror of insider buying.
- **`buyback`** — issuer repurchase programs: XBRL spend history
  (`PaymentsForRepurchaseOfCommonStock`), authorized/remaining amounts, and 8-K/
  exhibit announcements.
- **`8k`** — event stream by item code (2.02 earnings, 4.01 auditor change,
  4.02 non-reliance, 1.01 material agreements, 5.02 officer changes...) with
  `--has` filtering.
- **`ftd`** — SEC Fails-to-Deliver: the twice-monthly official data behind
  squeeze screens, aggregated by fails-$ with per-symbol history.
- **`short`** — FINRA consolidated short interest ranked by days-to-cover
  (keyless historical slice; current biweekly data via optional free API key).
- **`options`** — unusual options activity from live chains: volume-vs-OI flags,
  put/call ratios, and IV skew (yfinance, free).
- **`fomc`** — Hawkish/dovish sentiment scoring of Fed statements with stance-shift
  diffs between meetings, minutes, the meeting calendar — and `fomc odds`:
  market-implied rate-decision probabilities from Polymarket's live FOMC markets.
- **`fred`** — 56 curated aliases over 800K+ FRED series, macro dashboard, and a
  yield-curve command with inversion spreads.
- **`gappers`** — Premarket gap scanner with catalyst headlines.
- **`scan`** — FULL-MARKET screening on Yahoo's server-side engine: ~90 filter
  fields across price/valuation/margins/short interest/ownership, any region
  (US, JP...). No ticker list required — discovers candidates from the universe.
- **`ticker` / `sec` / `compare` / `screen`** — fundamentals, XBRL concepts
  (`--concept revenue`), side-by-sides, and a PEG-aware screener. Japanese listings
  (`7203.T`, `6758.T`...) work end-to-end with correct ¥ formatting.

## Install

```bash
git clone https://github.com/ZN9-KYANT/finresearch.git
cd finresearch
pip install -e .

# optional: JS-rendered TradingView news for gappers catalysts
pip install -e ".[crawl4ai]"
```

Optional config (shared by `screen` and `insider scan`):

```bash
mkdir -p ~/.config/finresearch
# one ticker per line, # comments allowed
cat > ~/.config/finresearch/watchlist.txt <<'EOF'
NVDA
ASML
VST
EOF
# optional: FRED API key (free, https://fred.stlouisfed.org/docs/api/api_key.html)
echo "FRED_API_KEY=yourkey" > ~/.config/finresearch/.env && chmod 600 ~/.config/finresearch/.env
```

Without a watchlist file, list commands run on a small neutral demo set.
`FRED_API_KEY` is read from the environment, `~/.config/finresearch/.env`, or a
`.env` in the current directory. `FINRA_API_KEY` (free, https://finra.org/finra-data,
unlocks current short-interest data) and `FINRESEARCH_SEC_UA` are read from the
environment only. `FINRESEARCH_CONFIG_DIR` relocates the whole config directory.

## Built for agents and automation

finresearch is meant to be a tool that an agent calls or a scheduler runs
unattended. These are the guarantees it makes to that caller:

| Contract | What it means for an agent, script, or cron job |
|---|---|
| **Non-interactive** | No prompts, no pagers, no TTY assumptions. Safe under cron, CI, systemd/launchd timers, and tool-calling harnesses. |
| **JSON on stdout, everywhere** | Every command takes `--json`. stdout is then exactly one JSON document; progress lines, warnings, and `[skip]` notices go to stderr. Shapes and units for every command: [`docs/JSON.md`](docs/JSON.md). |
| **Predictable exit codes** | `0` success, `1` error (one `finresearch: error: …` line on stderr, nothing on stdout), `2` usage error. Unknown tickers, unreachable sources, and bad templates are errors; set `FINRESEARCH_DEBUG=1` for a traceback. |
| **Empty is not an error** | "Nothing found" comes back as valid JSON (`[]`, `{"results": []}`) with exit 0, so `jq -e 'length > 0'` makes a clean alert condition. |
| **Raw values, explicit units** | JSON carries unformatted numbers. `ticker --json` names its `currency` (listing) and `financial_currency` (reporting). Unit contracts (percent vs fraction, 13F value units) are documented in [`AGENTS.md`](AGENTS.md). |
| **Keyless by default** | Every command except `fred` runs with zero setup. Optional keys come from the environment, so they fit secret managers and crontab env lines. |
| **Per-job isolation** | `FINRESEARCH_CONFIG_DIR=/path/to/job` gives each agent or job its own watchlist, scan templates, and `.env`. |
| **Saved queries** | An agent designs a screen once (`scan NAME --save`); a cron job reruns it by name indefinitely (`scan NAME --json`). |
| **Self-describing** | `finresearch --help` and `<command> --help` at every level, so agents can discover the tool surface; `--version` lets pipelines pin behaviour. |
| **Polite when unattended** | One paced fetcher keeps SEC traffic under 10 req/s with a declared User-Agent. FRED fetches only the observations it shows. 8-K item codes come from one feed request, not per-filing downloads. |

Without `--json`, every command prints human-readable markdown with the same
exit codes.

### Calling it from an agent

Any agent framework that can run a shell command or a subprocess can use it as a
tool. A minimal Python wrapper:

```python
import json, subprocess

def finresearch(*args):
    """Run a finresearch command and return its parsed JSON (stderr = diagnostics)."""
    proc = subprocess.run(["finresearch", *args, "--json"],
                          capture_output=True, text=True, check=True, timeout=300)
    return json.loads(proc.stdout)

trades = finresearch("insider", "scan", "--tickers", "NVDA,AMD,MU", "--days", "7")
movers = finresearch("scan", "--day-chg-min", "5", "--volume-min", "5000000")
```

Give the agent `finresearch --help` (or this README) as the tool description, and
[`docs/JSON.md`](docs/JSON.md) as the schema for what comes back; each
subcommand's `--help` lists its flags and units. With `check=True`, an error
raises `CalledProcessError` whose `stderr` holds the one-line reason.

### Scheduled research (cron)

It's just a command, so cron, systemd timers, launchd, GitHub Actions schedules,
or an agent's own scheduler all work. Cron runs with a minimal environment: use
absolute paths, set keys as crontab variables, and escape `%` as `\%`.

```cron
# Times are this machine's local time (these examples assume US/Eastern market hours).
FR=/home/you/finresearch/.venv/bin/finresearch
OUT=/home/you/research
FINRESEARCH_SEC_UA=my-research-bot/1.0 you@example.com

# 08:45 Mon–Fri: premarket gappers (each run is also saved to ~/.cache/finresearch/gappers/)
45 8 * * 1-5  $FR gappers --json > $OUT/gappers-$(date +\%F).json 2>> $OUT/cron.log

# 18:30 Mon–Fri: open-market insider buys/sells across the watchlist
30 18 * * 1-5 $FR insider scan --days 1 --json > $OUT/insiders-$(date +\%F).json 2>> $OUT/cron.log

# 07:00 daily: alert only when an auditor change (4.01) or non-reliance (4.02) 8-K lands
0 7 * * *     $FR 8k NVDA,AMD,MU --days 1 --has 4.01,4.02 --json | jq -e 'length > 0' >/dev/null && echo "restatement-risk 8-K filed" | mail -s finresearch you@example.com

# 07:15 daily: market-implied FOMC odds snapshot
15 7 * * *    $FR fomc odds --json > $OUT/fomc-odds-$(date +\%F).json 2>> $OUT/cron.log

# Sundays 10:00: rerun a saved full-market screen (quality-dip ships in examples/scans.toml)
0 10 * * 0    $FR scan quality-dip --json > $OUT/quality-dip-$(date +\%F).json 2>> $OUT/cron.log
```

### Pipelines (jq)

```bash
finresearch scan quality-dip --json | jq -r '.results[].symbol'          # tickers for the next step
finresearch insider scan --days 14 --json \
  | jq -r '.[] | select(.transactions | length > 0) | "\(.ticker): \(.transactions | length) trades"'
finresearch gappers --json --no-catalyst | jq -r '.gappers[] | "\(.symbol) \(.premarket_gap_pct)%"'
finresearch fomc odds --limit 1 --json \
  | jq -r '.[0] | "\(.meeting): " + ([.buckets | to_entries[] | "\(.key) \(.value*100|round)%"] | join(", "))'
```

### Rate etiquette for unattended runs

- **SEC EDGAR** is paced internally (≤10 req/s). For scheduled or heavy use, set
  `FINRESEARCH_SEC_UA` to a real contact so SEC can reach you instead of
  blocking you. Keep `insider`/`13f` back-scans to a modest `--days`.
- **FRED** allows 120 requests/minute. A full `fred dashboard` uses about 40, so
  don't run it more than about once a minute.
- **Yahoo-backed commands** (`ticker`, `compare`, `screen`, `scan`, `options`) use
  an unofficial endpoint that is rate-sensitive. Schedule them, don't loop them,
  and space jobs a few minutes apart.

### Coding agents working on this repo

`AGENTS.md` at the root carries the guidance every coding agent should follow:
setup, verify gates, architecture, and unit contracts. It is read natively by
Codex, Grok, pi, and Hermes; Claude Code reads `CLAUDE.md`, a symlink to it. One
command links everything for a fresh clone:

```bash
./scripts/install-agent-files.sh   # links CLAUDE.md, writes .cursor rule
```

## Ownership & flow commands (SEC EDGAR)

```bash
finresearch insider scan --tickers NVDA,AMD,MU --days 7 --min-value 100000
finresearch insider detail META --days 30         # every Form 4 transaction, one company
finresearch 13f holder BRK-B --top 15             # one filer's latest book (quarter-end marks)
finresearch 13f who NVIDIA CORP                   # which filers hold an issuer
finresearch 13f diff NOKIA CORP --limit 15        # QoQ adds / exits / buys / sells per filer
finresearch activist NOK,SPCX --days 400          # SC 13D/G stakes (activist vs passive)
finresearch dilution VST,NVDA --days 365          # S-3 shelves + 424B priced offerings
finresearch buyback NVDA,VST --days 400           # repurchase spend (XBRL) + announcements
finresearch 8k NVDA --days 60 --has 2.02,4.02     # 8-K event stream by item code
```

## Command reference

### Ticker data (yfinance)

```bash
finresearch ticker VST                          # overview
finresearch ticker VST --section financials     # income statement, balance sheet, cash flow
finresearch ticker VST --section kpis           # EPS/revenue estimates, margins, PEG
finresearch ticker VST --section earnings       # history, surprises, upcoming dates
finresearch ticker VST --section insiders       # insider transactions (yfinance view)
finresearch ticker VST --section holdings       # institutional holders (yfinance view)
finresearch ticker VST --section technicals     # RSI, MACD, Bollinger, MAs, signals
finresearch ticker VST --json
```

### SEC EDGAR (structured XBRL + filings)

```bash
finresearch sec VST                        # key financial facts
finresearch sec VST --type 10-K            # filings by type
finresearch sec VST --concept revenue      # friendly alias -> XBRL tag time series
finresearch sec VST --concept NetIncomeLoss
```

### Insider trades (SEC EDGAR Form 4 — native)

```bash
finresearch insider scan --tickers NVDA,AMD,MU --days 7 --min-value 100000
finresearch insider scan                          # uses ~/.config/finresearch/watchlist.txt
finresearch insider detail META --days 30         # every Form 4 transaction, one company
finresearch insider detail META --json
```

Filters to open-market activity (codes P/S); grants, exercises, and withholding are
shown in `detail` with their codes for context. Data comes from `data.sec.gov`
submissions + the filings' own XML.

### Institutional holdings (SEC Form 13F-HR — native)

```bash
finresearch 13f holder BRK-B --top 15       # one filer's latest book (quarter-end marks)
finresearch 13f holder 0001067983 --json    # by CIK
finresearch 13f who NVIDIA CORP             # which filers hold an issuer (FTS over 13F-HR)
```

`13f` values are quarter-end marks. The `<value>` unit is whole dollars for filings
made since 2023-01-03 and thousands before that, but filers don't always comply;
finresearch compares each filing's implied per-share price with the real price
(falling back to the filing date) and states its conclusion in the header. `13f who` uses
EDGAR full-text search (10K-hit search-index cap; a paginated crawl roadmap exists).

### FOMC (Federal Reserve)

```bash
finresearch fomc calendar              # meeting calendar, next-meeting countdown
finresearch fomc statement             # latest statement, full text + sentiment score
finresearch fomc statement 2026-06-16  # specific meeting
finresearch fomc minutes --full        # minutes text (released ~3 weeks post-meeting)
finresearch fomc sentiment             # hawk/dove shift between the last two statements
finresearch fomc odds                  # market-implied decision probabilities (Polymarket)
finresearch fomc statement --json
```

`fomc odds` reads live prediction-market prices (rate buckets normalized to a
distribution). CME FedWatch itself is bot-blocked and ToS-restricted; Polymarket's
public Gamma API is the free market-implied equivalent.

### Institutional flow: fails, short interest, options

```bash
finresearch ftd top                            # biggest fails in the latest SEC file
finresearch ftd top --by quantity --min-quantity 10000
finresearch ftd sym GME --files 3              # one symbol's fails history
finresearch short --top 15                     # FINRA short interest by days-to-cover
finresearch short --by si --min-si 1000000
finresearch options NVDA                       # unusual activity + P/C + IV skew
finresearch options NVDA --vol-oi 2.0 --json
```

`ftd` is the official SEC twice-monthly dataset (no key). `short` works keyless on
the free historical slice; set `FINRA_API_KEY` (free) for current biweekly data.
`options` uses yfinance chains (delayed).

### FRED macro data

```bash
finresearch fred dashboard                       # rates, inflation, employment, GDP...
finresearch fred dashboard --group inflation
finresearch fred series fed_funds --years 2
finresearch fred yield_curve                     # full curve + 2s10s/3m10s spreads
finresearch fred search "housing" --limit 10
finresearch fred list                            # all 56 aliases
```

### Screening & comparison

```bash
finresearch compare VST WMB GEV CEG TLN
finresearch screen --tickers NVDA,AMD,MU --max-peg 2 --sort growth
finresearch screen                                    # watchlist from config file
```

### Full-market scan (server-side)

`scan` runs against the WHOLE market via Yahoo's server-side screener engine —
no ticker list required (unlike `screen`, which filters tickers you supply).
The query is executed server-side across thousands of listings and matched rows
come back in one call with a total match count.

```bash
finresearch scan [range-fields] [min/max-fields] [--sector X] [--industry X]
                 [--region us] [--sort FIELD] [--ascending] [--limit N] [--json]
```

#### Range fields (take LO and HI values, raw numbers)

```bash
--price 5 100        # intraday price band
--mktcap 2e9 2e10    # market cap band (2B–20B); listing currency for non-US regions (JPY for region jp)
```

#### Threshold fields (--name-min / --name-max)

Ratio filters take **percent numbers** — `--netmargin-min 20` means 20%
(Yahoo's ratio fields are percent-coded; verified live: margin > 20 keeps
~2,277 of ~10k names, margin > 0.2 keeps nearly all).

| Flag | Filters on | Unit |
|---|---|---|
| `--avgvol-min/max` | 3-month average daily volume | shares |
| `--volume-min/max` | today's volume | shares |
| `--day-chg-min/max` | today's price change | percent |
| `--pe-min/max` | trailing P/E | plain |
| `--peg-min/max` | PEG (5y) | plain |
| `--netmargin-min/max` | net income margin | percent |
| `--grossmargin-min/max` | gross margin | percent |
| `--ebitda-margin-min/max` | EBITDA margin | percent |
| `--revgrowth-min/max` | 1y revenue growth | percent |
| `--epsgrowth-min/max` | EPS growth | percent |
| `--roe-min/max` | return on equity | percent |
| `--shortfloat-min/max` | short % of float | percent |
| `--dtc-min/max` | days to cover short | days |
| `--inst-held-min/max` | institutional % held | percent |
| `--insider-held-min/max` | insider % held | percent |
| `--divyield-min/max` | forward dividend yield | percent |
| `--debteq-min/max` | debt / equity | plain |
| `--quickratio-min/max` | quick ratio | plain |
| `--altmanz-min/max` | Altman Z-score | plain |

#### Other options

```bash
--region us          # us, jp, gb, de, fr, hk, kr, tw, in, ca, au ... (58 Yahoo regions)
--sector financial   # fuzzy-matched against Yahoo's sector vocabulary
--industry banks     # fuzzy-matched; unknown value prints matching candidates
--sort FIELD         # mktcap (default), price, day-chg, volume, pe, peg, netmargin,
                     # revgrowth, shortfloat, perf-52w
--ascending          # ascending sort (default: descending)
--limit 20           # rows fetched; Yahoo page cap 250
--within-high 0.25   # keep within 25% of the 52w high (FRACTIONS, client-side)
--below-high 0.2     # keep at least 20% below the 52w high (dip-band upper edge)
--off-low 0.3        # keep at least 30% above the 52w low (Minervini-style)
--json               # machine output: {"total", "dropped_by_post_filter", "results"}
```

The three 52w-extreme filters (`--within-high/--below-high/--off-low`) run
CLIENT-side on the fetched page because Yahoo's screener cannot query
distance-from-extreme server-side — pair them with `--limit 250` so the page
carries enough candidates before trimming (the dropped count is printed, and
`total` still shows the pre-filter match count).

#### Recipes

```bash
# value with liquidity: $5–100, real volume, cheap, some analyst short interest
finresearch scan --price 5 100 --avgvol-min 500000 --pe-min 8 --shortfloat-min 5

# short-squeeze watch: high short %, days-to-cover piling up, not micro-cap
finresearch scan --shortfloat-min 15 --dtc-min 4 --price 2 50 --sort shortfloat

# quality compounders: profitable, growing, low leverage
finresearch scan --netmargin-min 15 --revgrowth-min 10 --debteq-max 1 --pe-min 0

# dividend payers trading near lows
finresearch scan --divyield-min 4 --price 5 200 --avgvol-min 2000000

# Japan mega-caps (JPY caps: enter raw yen, e.g. 5T = 5e12)
finresearch scan --region jp --mktcap 5e12 1e14 --sort mktcap

# momentum day-list: biggest movers with real volume
finresearch scan --day-chg-min 5 --volume-min 5000000 --sort day-chg
```

Notes: results up to 250 per call (Yahoo page cap) and the true total match
count is always printed; data is Yahoo (unofficial, delayed). Under the hood it
is yfinance's screener engine, so no API key is needed — but it shares Yahoo's
rate sensitivity: scheduled runs are fine, tight loops are not (see
[rate etiquette](#rate-etiquette-for-unattended-runs)).

#### Named scan templates (save your scans)

Custom scans are saved as TOML templates in `~/.config/finresearch/scans.toml`,
then run by name. Keys mirror the CLI flags exactly (without `--`).

```bash
# interactively build + save: run with filters, add --save NAME2 --desc
finresearch scan --price 5 100 --avgvol-min 500000 --shortfloat-min 5 --save value2 --desc "cheap, liquid, shorted"
finresearch scan value2                     # run it
finresearch scan                            # list all saved templates
finresearch scan value2 --limit 40          # CLI flags override template values
finresearch scan value2 --netmargin-min 10 --save value3   # derive + save variant
```

`scans.toml` format (hand-editable too):

```toml
[value2]
description = "cheap, liquid, shorted"
price = [5.0, 100.0]        # range field: a [lo, hi] pair
avgvol-min = 500000
shortfloat-min = 5.0
sort = "shortfloat"

[jp-mega]
description = "Japan large caps, cheap"
region = "jp"
mktcap = [5e12, 1e14]
pe-max = 12
```

Precedence: template fills any filter you didn't set on the command line, so
one-off overrides (`--limit`, a tighter threshold) compose naturally. Unknown
template names list what's saved with a hint; unknown TOML keys are rejected
with the valid-key list before any query runs.

**Ready-made examples:** [`examples/scans.toml`](examples/scans.toml) ships
seven templates adapted from well-known public methodologies — momentum
breakouts (Qullamaggie-style), Minervini trend template, CAN SLIM proxy,
quality-dip (quality-on-sale), daily movers, heaviest volume, and a Japan
quality screen — each annotated with what the screener engine CANNOT express
(RS percentile, MA stacks, estimate revisions) and pointers for the manual
follow-up. See [examples/README.md](examples/README.md).

Install them:

```bash
cat examples/scans.toml >> ~/.config/finresearch/scans.toml
finresearch scan                      # the seven appear in your template list
finresearch scan quality-dip          # run one; any flag still overrides
```

See [`CHANGELOG.md`](CHANGELOG.md) for the release history.

### Premarket gappers

```bash
finresearch gappers                                  # top 10 with catalyst headlines
finresearch gappers --min-gap 5 --min-price 3 --min-volume 50000
finresearch gappers --no-catalyst                    # faster
finresearch gappers --catalyst crawl4ai              # TradingView news (needs crawl4ai)
finresearch gappers --json --no-catalyst             # piping / agents (= --format json)
```

Each run also saves its JSON to `~/.cache/finresearch/gappers/` (override with
`--output-dir`).

## Data sources & terms of use

| Source | Used by | Access model |
|---|---|---|
| SEC EDGAR (`data.sec.gov`, `www.sec.gov`, `efts.sec.gov`) | `sec`, `insider`, `13f`, `activist`, `dilution`, `buyback`, `8k`, `ftd` | Official public API; declared User-Agent; ≤10 req/s honored |
| SEC FTD files (`www.sec.gov/files/data/fails-deliver-data`) | `ftd` | Official public dataset, twice-monthly zips |
| FINRA API (`api.finra.org`) | `short` | Keyless historical slice; free API key for current data |
| Federal Reserve (`federalreserve.gov`) | `fomc` | Public pages, cached-friendly pacing |
| FRED (`fred.stlouisfed.org`) | `fred` | Official API; free key; 120 req/min honored |
| Yahoo Finance (via **yfinance**) | `ticker`, `compare`, `screen`, `options`, JP listings | Unofficial community endpoint; delayed data |
| Polymarket (Gamma API) | `fomc odds` | Public prediction-market API, no auth |
| TradingView / StockAnalysis / Google Finance | `gappers`, catalysts | Public web pages (SSR); unofficial |

**Accuracy & terms notices.** Yahoo Finance access through yfinance is unofficial and
subject to Yahoo's terms; TradingView/StockAnalysis/Google Finance data is scraped from
public pages and is unofficial. Financial figures may be delayed (quotes up to 15
minutes late), preliminary, or occasionally wrong at the source; verify anything you
act on against the cited primary source. This tool is for research and education — not
investment advice, and not a market-data Redistribution service: keep fetched data
inside your own analysis, don't republish or resell provider data. All sources are
accessed through their documented public surfaces at compliant rates.

`SEC EDGAR` fair-access requires a declared contact string. The default User-Agent is
`finresearch/<version> contact@example.com`; set
`FINRESEARCH_SEC_UA="your-tool/1.0 you@yourdomain.com"` for scheduled or heavy use.

## Tests & CI

```bash
pip install -e ".[dev]"
pytest tests/          # scorer, parsers, unit-detection, formatters, technicals
ruff check src/ tests/
```

CI runs tests + ruff + a gitleaks secret scan on every push/PR (Python 3.10 and 3.12).
Contributing with a coding agent? See
[Coding agents working on this repo](#coding-agents-working-on-this-repo).

## License

[MIT](LICENSE)