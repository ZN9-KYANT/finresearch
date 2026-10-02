# JSON output reference

Every finresearch command takes `--json` (`gappers` also accepts `--format json`).
This page is the contract for agents, scripts, and cron jobs that consume it.

## Output contract

| Situation | stdout | stderr | exit |
|---|---|---|---|
| Success | exactly one JSON document | progress, warnings, `[skip]` notices | `0` |
| Nothing found | valid empty JSON (`[]`, `"rows": []`, …) | — | `0` |
| Error (unknown ticker, no data at all, upstream unreachable, bad template…) | nothing | one line: `finresearch: error: …` | `1` |
| Usage error (bad flag, missing argument, family without subcommand) | nothing | argparse usage text | `2` |
| Interrupted (Ctrl-C) | — | — | `130` |

- Multi-ticker commands tolerate partial failure. `insider scan`, `activist`,
  `dilution`, `buyback`, and `8k` skip unknown tickers with a `[skip]` notice on
  stderr; `compare` and `screen` report them as per-ticker `error` entries. They
  fail (exit 1) only when **no** ticker yields data.
- Set `FINRESEARCH_DEBUG=1` to get the Python traceback instead of the one-line
  error. Credentials that ride in URLs (FRED `api_key=`) are masked in error text.
- Text mode (no `--json`) follows the same exit codes and stderr rules.

## Conventions

- **Numbers are raw**: no currency symbols, no `B`/`M` suffixes, no rounding
  for display. Missing values are `null`.
- **Ratios are fractions** (`0.276` = 27.6%) unless the key says `_pct`, which
  means percent points (`3.35` = 3.35%). Two Yahoo pass-through exceptions:
  `dividend_yield` (`ticker`) and `regularMarketChangePercent` (`scan`
  results) are percent points.
- **Dates** are ISO strings (`YYYY-MM-DD`; timestamps ISO 8601).
- **Currencies**: `ticker` and `compare` name both `currency` (listing:
  prices, market cap, EPS, targets) and `financial_currency` (reporting:
  revenue, EBITDA, FCF, statements). SEC-derived dollar values are USD.
- **As-filed values**: Form 4 transaction fields (`shares`, `price`,
  `post_shares`) are the strings in the filing; computed values (`value`) are
  numbers.
- **Pass-through objects**: `scan` results are Yahoo screener quote objects as
  returned (field set varies by listing); `fomc statement`/`minutes` carry
  the source text.

## Commands

### Market data (Yahoo Finance)

**`ticker SYMBOL --json [--section S]`** → object. Always: `ticker`, `currency`,
`financial_currency`, `quote_type`. Then, by section (`all` = every key below):

| Section | Keys |
|---|---|
| `overview` | `overview` {`name`, `sector`, `industry`, `market_cap`, `employees`, `website`, `price`, `52w_high`, `52w_low`, `50d_ma`, `200d_ma`, `avg_volume`, `shares_outstanding`, `float_shares`, `short_pct_float` (fraction), `short_ratio` (days)}, `valuation` {`eps_ttm`, `eps_fwd`, `pe_ttm`, `pe_fwd`, `peg_ratio`, `price_to_book`, `ev_to_ebitda`, `ev_to_revenue`, `dividend_yield` (percent points), `payout_ratio`}, `profitability` {`revenue`, `gross_profit`, `ebitda`, `gross_margin`, `operating_margin`, `profit_margin`, `roe`, `roa`, `debt_to_equity`}, `analyst` {`target_mean`, `target_median`, `target_high`, `target_low`, `num_analysts`, `recommendation`} |
| `financials` | `financials` {`annual_income`, `quarterly_income`, `annual_balance`, `quarterly_balance`, `annual_cashflow`, `quarterly_cashflow`}: each `{line item: {period end: value}}`, last 4 periods, reporting currency |
| `kpis` | `kpis` {`eps_estimates`, `revenue_estimates`}: `[{period, avg, low, high, growth}]` |
| `earnings` | `earnings` {`history`: `[{quarter, eps_actual, eps_estimate, surprise_pct (fraction), beat}]`, `calendar`: {`next_earnings`, `eps_avg`, `eps_high`, `eps_low`, `revenue_avg`, `ex_dividend`}} |
| `insiders` | `insiders` {`transactions`: `[{insider, position, transaction, shares, date}]`, `purchase_summary`: {label: value}, `major_holders`: {label: value}} |
| `holdings` | `holdings` {`institutional`: `[{holder, pct_held, shares, value, pct_change, date_reported}]`, `mutual_funds`: `[{holder, pct_held, date_reported}]`} |
| `technicals` | `technicals` {`current_price`, `rsi_14`, `macd` {`macd_line`, `signal_line`, `histogram`}, `bollinger` {`upper`, `middle`, `lower`}, `support`, `resistance`, `atr_14`, `moving_averages` {`ma_20`, `ma_50`, `ma_200`}, `price_changes` {`1d_pct`, `1w_pct`, `1m_pct`}, `range_52w` {`high`, `low`, `position_pct`}, `volume` {`current`, `avg_20d`}, `signals`: [str]} |

**`compare A B … --json`** → `[{ticker, name, currency, financial_currency, price,
market_cap, pe_ttm, pe_fwd, profit_margin, revenue, ebitda, free_cashflow,
num_analysts, target_mean}]`. A ticker without data appears as
`{ticker, error}`.

**`screen --json`** → `{query: {tickers, filters, sort}, total_scanned,
total_passing, results: [{ticker, name, sector, industry, price, market_cap,
trailing_pe, forward_pe, peg_ratio, revenue, revenue_growth, gross_margin,
operating_margin, profit_margin, debt_to_equity, roe, fcf, target_mean, analysts,
recommendation, beta, dividend_yield (fraction), currency}], excluded: [{ticker,
name}], errors: [{ticker, error}]}`.

**`scan … --json`** → `{total, dropped_by_post_filter, results: [Yahoo quote
objects]}`. `total` is the server-side match count before `--limit`.
**`scan --json`** (no name, no filters) → `{path, templates: {name: {description,
valid, config}}}`. **`scan NAME --save --json`** → `{saved, replaced, path, config}`.

**`options SYMBOL --json`** → `{ticker, expiries: [str], totals: [{expiry,
call_vol, put_vol, pc_vol_ratio, call_oi, put_oi, pc_oi_ratio, iv_call_avg,
iv_put_avg, iv_skew}], unusual: [{expiry, side, strike, last, bid, ask, iv,
volume, oi, vol_oi}]}`. IVs are fractions. No chains → empty arrays.

**`news SYMBOL --json`** → `{ticker, exchange, name, price, headlines: [{title,
url}], source}`. `price` is `null` where Google Finance shows none (e.g. ETFs).

**`gappers --json`** → `{scanned_at, source, total_raw, gappers: [{rank, symbol,
ticker, exchange, name, premarket_gap_pct, premarket_price, premarket_chg,
premarket_chg_pct, premarket_volume, close_price, chg_pct, volume, mkt_cap (as
displayed by the source), mkt_cap_perf_1y, source, catalyst, headlines: [str]}]}`.

**`transcript SYMBOL --json`** → `{ticker, transcripts_url, symbol_url,
scrape_hint}` (links only; transcripts are not redistributed).

### SEC EDGAR

**`sec SYMBOL --json`** → `{ticker, cik, company, facts: [{label, tag, unit, value,
period_end}], revenue_history: [observation]}`.
**`sec SYMBOL --type FORM --json`** → `{ticker, cik, company, form, filings:
[{form, filing_date, accession, primary_document}]}` (newest 10).
**`sec SYMBOL --concept C --json`** → `{ticker, cik, company, concept, unit,
observations: [observation]}`: the full history (the table shows the last 12).
An observation is `{start, end, value, form, filed, fiscal_year, fiscal_period}`.

**`insider scan --json`** → `[{ticker, company, transactions: [{ticker, insider,
roles, side (BUY|SELL), code, date, shares, price, value}]}]`.
**`insider detail SYMBOL --json`** → `{ticker, company, filings: [{issuer,
issuer_cik, insider, roles: [str], accession, filing_date, transactions: [{kind,
security, code, date, shares, price, acquired_disposed, post_shares, direct}]}]}`.

**`13f holder FILER --json`** → `{holder, cik, accession, filed, period,
value_scale: {factor, reason}, rows: [{issuer, cusip, type, shares, putCall,
value_usd}]}`. `value_usd` is whole dollars after scale detection.
**`13f who WORDS --json`** → `{issuer, total_raw_hits: {value, relation}, filers:
[{cik, filer, accession, file, file_date, period_ending}]}`.
**`13f diff WORDS --json`** → `{issuer, rows: [{filer, filer_cik, period_prev,
period_now, shares_prev, shares_now, delta_shares, value_now_usd, action}]}`;
`action` ∈ `ADDED`, `EXITED`, `BOUGHT`, `SELL`, `SAME`.

**`activist --json`** → `[{ticker, form, filed, filer, flag (activist|passive|
unparsed), accession}]`.
**`dilution --json`** → `[{ticker, form, filed, shares_hint, size_hint, atm,
accession}]` (hints are text fragments from the prospectus).
**`buyback --json`** → `[{ticker, history: {spend: [{start, end, amount_usd,
form}], authorized, remaining} | null, announcements: [{ticker, filed, note,
source}]}]`.
**`8k --json`** → `[{ticker, form, filed, items: [str], summary, accession}]`.

**`ftd top --json`** → `{file, rows, top: [{symbol, description, peak_date,
peak_quantity, peak_value_usd, price}]}` (`price` = previous close).
**`ftd sym SYMBOL --json`** → `[{settlement_date, cusip, symbol, quantity_fails,
description, price}]`.

### Short interest (FINRA)

**`short --json`** → `{mode, rows: [{symbol, name, settlement_date,
short_interest, prev_short_interest, adv, days_to_cover, change_pct}]}`.
`days_to_cover` is `null` where FINRA reports its 999.99 no-volume sentinel;
`mode` says whether rows are current (keyed) or the keyless historical slice.

### Macro (FRED, Federal Reserve, Polymarket)

**`fred series NAME --json`** → `{series_id, title, units, count, observations:
[{date, value}]}`. `*_yoy` aliases report `units: "Percent Change from Year Ago"`.
**`fred dashboard --json`** → `{updated, groups: {group: [point]}}`.
A point is `{series_id, available, title, units, frequency, date, value,
prev_date, prev_value, change, change_pct}`; unavailable series are
`{series_id, available: false}`.
**`fred yield_curve --json`** → `{curve: [{tenor, series_id, date, yield_pct}],
spreads_pct: {"10Y-2Y", "10Y-3M"}, inverted: {"10Y-2Y", "10Y-3M"}}`.
**`fred search Q --json`** → `[{id, title, frequency, units, seasonal_adjustment}]`.
**`fred list --json`** (offline, no key) → `{aliases: {alias: {series_id,
transform}}, categories: {category: [alias]}}`.

**`fomc calendar --json`** → `{next_meeting: {date, end} | null, meetings: [{date,
end, sep, year, minutes_date, status (past|future)}]}`.
**`fomc statement --json`** → `{meeting_date, end_date, url, statement,
sentiment}`; **`fomc minutes --json`** → `{meeting_date, minutes_date, url,
minutes}`.
**`fomc sentiment --json`** → `{current_meeting, previous_meeting,
current_sentiment, previous_sentiment, stance_shift: {from, to,
hawkish_score_change, dovish_score_change}, phrase_changes: [{phrase, prev, curr,
change, direction}], hawkish_term_changes: [{term, prev, curr, change}],
dovish_term_changes: [...]}`.
A sentiment is `{stance, hawkish_score, dovish_score, hawkish_pct, dovish_pct,
hawkish_terms: {term: {count, weight, score}}, dovish_terms: {...}}`.
**`fomc odds --json`** → `[{meeting, end_date, volume, buckets: {label:
probability}}]`. Probabilities are 0–1, normalized to sum to 1 per meeting.
