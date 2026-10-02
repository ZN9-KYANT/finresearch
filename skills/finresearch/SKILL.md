---
name: finresearch
description: Financial research from free, official sources via the `finresearch` CLI. Covers SEC EDGAR filings (insider Form 4 trades, 13F institutional holdings, 13D/G activist stakes, S-3/424B dilution, buybacks, 8-K events, fails-to-deliver), FINRA short interest, options flow, US and Japanese stock fundamentals and technicals, full-market stock screening, FRED macro data, FOMC statements, sentiment and market-implied rate odds, premarket gappers, and news. Use when the user asks about a stock or company, insider or institutional buying and selling, SEC filings, screening for stocks, macro indicators, the Fed, or wants recurring/automated market research. Every command returns JSON with --json.
---

# finresearch

`finresearch` is a CLI built to be called by agents. Every command takes
`--json`, never prompts, and follows one output contract. This skill tells you
which command answers which question, how to call it, and how to read the
results correctly.

## 1. Before the first call

```bash
finresearch --version        # 1.1.0+ required: --json on every command
```

- Not installed? From a clone: `pip install -e .` (or `uv pip install -e .`).
- **No keys needed** for anything except `fred` (free key, `FRED_API_KEY` in the
  environment or `~/.config/finresearch/.env`). `FINRA_API_KEY` is optional
  (current short interest). `FINRESEARCH_SEC_UA="tool/1.0 you@domain"` should be
  set for heavy or scheduled SEC use.
- Optional watchlist: `~/.config/finresearch/watchlist.txt`, one ticker per
  line. `insider scan` and `screen` use it when no tickers are given; without it
  they fall back to a small demo list (AAPL, MSFT, NVDA, AMZN, GOOGL, META).
  Don't present demo-list results as the user's watchlist.

## 2. How to call it

Always add `--json` and parse stdout. Read stderr only for diagnostics.

| Exit | Meaning | What to do |
|---|---|---|
| `0` | Success. stdout is exactly one JSON document. Empty (`[]`, `"rows": []`) means "nothing found", which is a valid answer. | Use it. Say "none found" rather than retrying. |
| `1` | Error. stdout is empty; stderr has one line `finresearch: error: …` (unknown ticker, no data, source unreachable, bad template). | Report or fix the input (check the ticker spelling and exchange). Retry only for network-type errors, after a pause. |
| `2` | Usage error (bad flag, missing argument, family without subcommand). | Fix the invocation; `finresearch <cmd> --help` lists flags. |

- `[skip] TICKER: …` lines on stderr mean that ticker was skipped in a
  multi-ticker call; the rest still ran.
- Run one command at a time; don't fan out many parallel calls (see §7).
- Shapes for every command: `references/JSON.md` (next to this file).

## 3. Which command answers which question

| The user wants… | Command |
|---|---|
| Snapshot of a company: price, valuation, margins, analyst targets | `ticker SYM --json` |
| Financial statements / estimates / earnings history / holders | `ticker SYM --section financials\|kpis\|earnings\|insiders\|holdings\|all --json` |
| Technicals: RSI, MACD, Bollinger, MAs, support/resistance | `ticker SYM --section technicals --json` |
| Side-by-side of several tickers | `compare A B C --json` |
| Official reported figures (XBRL) or a metric's history | `sec SYM --json`, `sec SYM --concept revenue --json` |
| A company's recent filings of one form type | `sec SYM --type 10-K --json` |
| Are insiders buying or selling? | `insider scan --tickers A,B --days 30 --json` (open-market P/S only); `insider detail SYM --days 90 --json` (every Form 4 code) |
| What does a fund hold? | `13f holder BRK-B --json` (ticker or 10-digit CIK of the filer) |
| Which institutions hold / added / exited a stock? | `13f who NVIDIA CORP --json`, `13f diff NVIDIA CORP --json` (issuer name as filed, not ticker) |
| Activist stakes (5%+ holders) | `activist SYM --json` |
| Share issuance risk (shelves, offerings, ATM programs) | `dilution SYM --json` |
| Buyback programs and actual repurchase spend | `buyback SYM --json` |
| Material events (earnings, auditor change, exec departures…) | `8k SYM --days 90 --json`, filter with `--has 4.01,4.02` |
| Short squeeze inputs | `short --json`, `ftd top --json`, `ftd sym SYM --json`, `scan --shortfloat-min 15 --json` |
| Unusual options activity, put/call, IV skew | `options SYM --json` |
| Find stocks matching criteria across the whole market | `scan … --json` (server-side, no ticker list needed) |
| Filter a given list of tickers by fundamentals | `screen --tickers A,B,C … --json` |
| Today's premarket movers with headlines | `gappers --json` |
| Recent headlines for a ticker | `news SYM --json` |
| Macro snapshot | `fred dashboard --json`, `fred yield_curve --json` |
| One macro series (CPI YoY, unemployment, 10Y…) | `fred series cpi_yoy --json` (aliases: `fred list --json`; any FRED ID works) |
| Find a FRED series | `fred search "housing starts" --json` |
| Fed: next meeting, statement, minutes, tone shift | `fomc calendar --json`, `fomc statement --json`, `fomc minutes --json`, `fomc sentiment --json` |
| Market-implied odds of the next rate decision | `fomc odds --json` |
| Earnings call transcripts | `transcript SYM --json` (links only) |

## 4. Command details that matter

**Tickers.** US symbols as usual (`BRK-B`, not `BRK.B`). Japanese listings use
Yahoo's `.T` suffix (`7203.T`, `6758.T`) and work in `ticker`, `compare`,
`screen`, and `scan --region jp`. SEC, FINRA, FTD, 13F and `options` data is
**US-only**.

**`scan`**: the whole market, filtered server-side.
- Ranges take two numbers: `--price LO HI`, `--mktcap LO HI` (listing currency:
  yen for `--region jp`, so 5 trillion yen is `5e12`).
- Thresholds take `--FIELD-min` / `--FIELD-max`. Fields: `avgvol`, `volume`,
  `day-chg`, `pe`, `peg`, `netmargin`, `grossmargin`, `ebitda-margin`,
  `revgrowth`, `epsgrowth`, `roe`, `shortfloat`, `dtc`, `inst-held`,
  `insider-held`, `divyield`, `debteq`, `quickratio`, `altmanz`, `beta`, `pb`,
  `perf-52w`.
- **Ratio filters take percent numbers**: `--netmargin-min 20` means 20%, not
  0.2. Raw: `pe`, `peg`, `beta`, `pb`, `dtc`, `debteq`, `quickratio`,
  `altmanz`, volumes.
- `--region` (59 Yahoo regions: `us`, `jp`, `gb`, `de`, `hk`, `kr`, `tw`, `in`,
  `ca`, `au`, …), `--sector`/`--industry` (fuzzy; an unknown value errors with
  candidates), `--sort` (`mktcap` default, `price`, `day-chg`, `volume`, `pe`,
  `peg`, `netmargin`, `revgrowth`, `shortfloat`, `perf-52w`), `--ascending`,
  `--limit` (max 250).
- 52-week distance filters run client-side on the fetched page and take
  **fractions**: `--within-high 0.25`, `--below-high 0.2`, `--off-low 0.3`. Use
  them with `--limit 250`. `dropped_by_post_filter` tells you how many were cut.
- `total` in the result is the full match count; `results` holds at most
  `--limit` rows.
- Saved templates: `scan NAME --price 5 100 … --save --desc "why"` stores the
  query; `scan NAME --json` reruns it; `scan --json` lists templates. Ready-made
  examples ship in the repo's `examples/scans.toml`.

**`screen`** filters a ticker list you supply (or the watchlist). Thresholds:
`--min/max-pe`, `--min/max-fwd-pe`, `--min/max-peg`, `--min-revgrowth`
and `--min-margin` (percent numbers), `--max-debt-equity`, `--min/max-mktcap`,
`--min/max-beta`, `--sector`, `--industry`. A ticker missing a metric fails
any filter on that metric.

**`insider scan`** reports only open-market purchases (`P`) and sales (`S`);
grants, option exercises and tax withholding are noise for sentiment.
`--min-value 100000` keeps meaningful trades. Keep `--days` modest (≤90):
each filing is a separate SEC request.

**`13f`**: `holder` takes the *filer's* ticker or CIK. `who`/`diff` take the
*issuer name as it appears in 13F tables* (`NVIDIA CORP`, `APPLE INC`), not a
ticker. Holdings are quarter-end snapshots filed up to 45 days after quarter
end, so they are always stale by 1.5–4.5 months.

**`8k --has`** item codes: 1.01 material agreement, 1.05 cybersecurity
incident, 2.02 earnings results, 2.05 restructuring costs, 2.06 impairment,
3.01 delisting notice, **4.01 auditor change, 4.02 non-reliance on prior
financials (restatement risk)**, 5.01 change in control, 5.02
director/officer change, 5.07 shareholder vote, 7.01 Reg FD, 8.01 other.

**`fred series NAME`**: `--days N`, `--years N`, `--start-date/--end-date
YYYY-MM-DD`, `--last N` (text rows only). With `--json` and no date range you
get the **full history**, which can be large for daily series; bound it with
`--days` or `--years`. `*_yoy` aliases (`cpi_yoy`, `pce_yoy`, `m2_yoy`) are
already percent change from a year ago.

**`fomc statement [DATE]`** / **`minutes [DATE]`**: DATE is a meeting's
start or end day (`2026-09-16`); a partial match like `2026-06` works. Default
is the latest. `minutes` appear about 3 weeks after a meeting.

**`gappers`** is meaningful during US premarket (about 04:00–09:30 ET).
Outside those hours the lists reflect the last premarket session; say so. Each run is also
saved under `~/.cache/finresearch/gappers/`.

**`short`** without `FINRA_API_KEY` returns FINRA's keyless **historical**
slice, frozen at one old settlement date. Check `mode` and `settlement_date`,
and never present it as current short interest.

## 5. Units and reading the numbers

- Numbers are raw (no `$`, no `B`/`M`); missing is `null`.
- **Fractions vs percent points**: ratios are fractions (`0.276` = 27.6%):
  margins, ROE, growth, payout, `short_pct_float`, holder `pct_held`,
  `surprise_pct`, options IV. Keys ending in `_pct` are percent points.
  Exceptions that are percent points: `ticker` `dividend_yield` and `scan`
  `regularMarketChangePercent`.
- **Two currencies** in `ticker`/`compare`: `currency` (listing: price, market
  cap, EPS, targets) and `financial_currency` (reporting: revenue, EBITDA, FCF,
  statements). They differ for ADRs: TSM trades in USD but reports in TWD.
  Always label the currency when you report a figure; Japanese listings are in
  JPY throughout.
- SEC-derived amounts (`13f` `value_usd`, `buyback`, `ftd`) are USD.
- Form 4 fields `shares`/`price` are strings exactly as filed; convert before
  doing arithmetic.
- `fomc odds` bucket probabilities are 0–1, normalized to sum to 1 per meeting.
- `fomc` sentiment is a keyword heuristic (hawkish vs dovish term counts).
  Present it as a rough signal, not a reading of policy.

## 6. Workflows

**Company deep-dive** (run sequentially):
1. `ticker SYM --json`: what it is, valuation, profitability, targets.
2. `ticker SYM --section earnings --json`: beats/misses, next earnings date.
3. `sec SYM --json` (US): official reported facts as a cross-check.
4. `insider scan --tickers SYM --days 90 --json`: insider conviction.
5. `8k SYM --days 90 --json`: recent material events; flag 4.01/4.02.
6. `dilution SYM --json` and `buyback SYM --json`: share count pressure.
7. `activist SYM --json`, `13f who "ISSUER NAME" --json`: who owns it.
8. `options SYM --json`, `news SYM --json`: positioning and catalysts.

**Find ideas** → `scan` with criteria (or a saved template) → take the top
`results[].symbol` → `compare` them → deep-dive the best one or two.

**Smart-money check** → `insider scan --tickers … --min-value 100000` +
`13f diff "ISSUER NAME"` + `activist`.

**Risk flags** → `8k SYM --has 4.01,4.02,1.05,3.01`, `dilution SYM`,
`ftd sym SYM`, `scan --shortfloat-min 20 --dtc-min 5`.

**Macro briefing** → `fred dashboard` + `fred yield_curve` (inversion flags)
+ `fomc calendar` (next meeting) + `fomc odds` + `fomc sentiment`.

**Japan** → `scan --region jp --mktcap 1e12 1e14 --pe-max 15 --json` →
`compare 7203.T 6758.T 9984.T --json` → `ticker 7203.T --section all --json`.
Remember JPY; SEC/13F/insider tools don't apply.

**Recurring research** → save a query with `scan NAME … --save`, then
schedule `finresearch scan NAME --json`, `insider scan --days 1 --json`, or
`8k … --days 1 --has 4.02 --json | jq -e 'length > 0'` in cron. Use absolute
paths, and escape `%` as `\%` inside crontab. `FINRESEARCH_CONFIG_DIR` gives
each job its own watchlist, templates and `.env`.

## 7. Limits and etiquette

- **SEC**: the tool paces itself under 10 req/s; still keep `insider`/`13f`/
  `8k` ticker lists and `--days` modest.
- **FRED**: 120 requests/min; `fred dashboard` uses about 40.
- **Yahoo-backed commands** (`ticker`, `compare`, `screen`, `scan`, `options`)
  use an unofficial endpoint. Don't loop them; space out bulk work.
- Data can be delayed (quotes up to ~15 min) or wrong at the source. For
  anything consequential, cite the primary source (the SEC filing, the FRED
  series) and its date.

## 8. Reporting results to the user

- State the source and as-of date (`filing_date`, `period`, observation
  `date`, `scanned_at`) next to each number, with units and currency.
- Say when data is structurally stale: 13F (quarter-end), keyless short
  interest (historical), FTD (twice monthly), FRED monthly series (about a
  month of lag).
- Treat an empty result as information ("no insider purchases in 90 days").
- This is research data, not investment advice; don't present screens or
  sentiment scores as recommendations.
