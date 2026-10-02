# finresearch scan — example templates

Ready-to-use named scans for `finresearch scan NAME`. Copy any `[section]`
into your `~/.config/finresearch/scans.toml` (the CLI merges: missing file →
create it; existing sections are kept).

```bash
cat examples/scans.toml >> ~/.config/finresearch/scans.toml  # or paste sections
finresearch scan                                # list what's saved
finresearch scan minervini-trend                # run one
finresearch scan minervini-trend --limit 5      # any flag overrides the template
```

These examples are **mechanical approximations** of well-known public
methodologies (Qullamaggie breakouts, Minervini's Trend Template, O'Neil's
CAN SLIM, quality-dip buying, Stockbee movers). Server-side screener fields
cannot express every guru rule (relative-strength percentile, MA-stacks,
estimate revisions), so each template notes what it CANNOT check — treat
results as a watchlist for chart work, not signals. Units: percent fields take
percent numbers (`netmargin-min = 20`), price/cap raw; `--below-high`,
`--within-high`, `--off-low` take fractions (`025` band = `below-high = 0.2`).

## The examples

| Template | Idea | Key filters |
|---|---|---|
| `qullamaggie-proxy` | momentum leaders near highs, liquid | `perf-52w-min`, `day-chg`, liquidity |
| `minervini-trend` | Stage-2 uptrend, near high, off lows | `within-high 0.25` + `off-low 0.3` |
| `canslim-proxy` | growth + quality + sponsorship | `epsgrowth-min 25`, `roe-min 15`, `inst-held-max 90` |
| `quality-dip` | sound business 20–50% off its high in a high-beta selloff | `below-high 0.2` + `within-high 0.5` + `beta 1.1+` |
| `stockbee-daily-movers` | today's range-expansion candidates | `day-chg-min 4`, real volume |
| `highest-volume-close` | unusual-volume names | `volume-min 5M` vs `avgvol-min` |
| `jp-quality` | the dip framework, JPY caps, Japan region | `region jp`, ¥ thresholds |

## What each CANNOT check (do the chart work)

- **RS percentile / IBD RS line** — no field; `perf-52w` + `day-chg` are the
  proxies here.
- **MA stacks (EMA10>SMA20>SMA50>SMA150>SMA200), 200-day rising** — MA shape is
  not queryable server-side. `ticker X --section technicals` prints them per name.
- **Forward estimate revisions (90d)** — the single highest-value quality-dip
  filter is manual: check the estimates tab per candidate. Price down + estimates
  flat/rising = multiple compression (what you want); estimates falling = falling
  knife (discard).
- **Relative drawdown vs SPY/QQQ (quality-dip tiers)** — approximate with the
  `below-high`/`within-high` band + `beta-min`; per-name compare vs the index.
- **VCP / flag geometry, sector relative strength** — manual.

## Tuning

- Liquidity floor too loose for your size? raise `avgvol-min` (shares) and add
  `mktcap` floors — e.g. institutional-size movers: `avgvol-min = 2000000`,
  `mktcap = [10000000000, 1e15]`.
- The 250-row page cap + client-side `within-high`-style filters interact:
  for `quality-dip`-style scans, keep `--limit`/`limit = 250` BEFORE the
  post-filter trims, or tight dip bands will drop rows the server already
  cut away (the output reports how many were dropped).
- Non-US: swap `region = "jp"` and remember caps/prices are in the LISTING
  currency (¥ thresholds like `mktcap = [3e11, 1e15]`).