# Pre-Bell

Tomorrow's opening gap, forming overnight on Base.

Wall Street sleeps. Base does not. Pre-Bell watches a tokenized stock trade
overnight on Base and shows the opening gap that is forming, then scores
itself when the bell rings at 9:30 AM ET.

Base Stocks Maxxing, Track 3 Programmable Stock Markets ($20,000 pool).
Built 2026-11-16. Prototype v2. No registration, no submission, no payment,
no mainnet deployment, no trades.

## The one flow

1. Pick a stock: NVDA, AAPL, or TSLA.
2. See the last US close, the live overnight price on Base, and the predicted
   opening gap in percent and dollars, as a gauge.
3. Watch the countdown to the 9:30 AM ET open, ticking live.
4. After the open, see the actual opening price and how close the overnight
   prediction got, as an accuracy score out of 100.

Two ways to see the accuracy reveal right now, without waiting for morning:

- **Ring the bell (demo open):** draws a demo open near the overnight price
  and scores the prediction against it.
- **Replay a real morning:** pick any of the last 64 mornings. The previous
  close and the real open are real. The overnight prediction is a fixed demo
  rule (60% of the real move), so the score shows how that rule would have
  done.

## How to run it

```
node server.js
```

Then open http://localhost:4194 in a browser. The page also works as a
static file, but then it shows the labelled snapshot instead of live prices.

## What is real, what is still mock

Real, fetched 2026-11-16 22:48:06 UTC (snapshot) and live after that:

- **Overnight price: REAL.** The Aerodrome Slipstream price of the Coinbase
  B20 token for that stock, from DexScreener (public API, CORS open), polled
  every 30 seconds. When the page is served by `node server.js` it comes
  through `GET /api/prices`; otherwise the browser calls DexScreener
  directly. If both fail, the page falls back to the labelled snapshot.
  Snapshot prices at 22:48 UTC: NVDA $156.14, AAPL $352.96, TSLA $378.76.
  Live at 22:50 UTC: NVDA $156.07, AAPL $352.96, TSLA $378.77. The price
  moves between fetches, which is itself proof it is live.
- **B20 token records: REAL.** From the free read-only Coinbase Tokenized
  Stocks API (`https://api.coinbase.com/v1/tokenized-stocks`, no key):
  NVDAc 0xb20000000000000000000078ee7ce2fE4908108C, multiplier 1.0005379,
  supply 53,389.38, first mint 2026-08-12;
  AAPLc 0xb200000000000000000000C2e324d24d7eEcd1fb, multiplier 1.0005004,
  supply 6,034.16, first mint 2026-08-12;
  TSLAc 0xb2000000000000000000001e800a7f5189430cD0, multiplier 1,
  supply 6,399.15, first mint 2026-09-03.
- **Chainlink NAV: REAL, read on-chain.** `latestRoundData` on Base public
  RPC (`https://mainnet.base.org`), feeds NVDA
  0x04689a41629776563E6822F76f2e57D148d28513, AAPL
  0x787f13dEa48Db0897CbCDD985de77809D837F988, TSLA
  0xFaf869185383a24F8cb00e27BdA6b63B9905DCb4. At 22:48 UTC: NVDA
  $156.30903961 (updated 21:53:33Z), AAPL $351.95552669 (updated
  19:21:33Z), TSLA $379.05499999 (updated 20:50:59Z). NAV matches the
  Coinbase API nav_price to the cent, as expected: both read the same
  Chainlink feed.
- **Daily closes and opens: REAL.** 65 trading days, 2026-08-17 to
  2026-11-16, from the Yahoo Finance chart API. Latest closes: NVDA
  $156.14, AAPL $352.78, TSLA $379.74, all 2026-11-16. The last 10 days
  match the v1 data exactly.
- **Overnight trading activity: REAL, and it is not thin.** Top Aerodrome
  pools at 22:46 UTC: NVDAc/USDC 0xF668e21993f0ACd7ab00BB1cFbAeD0df28A3C8EC,
  liquidity $1.46M, 24h volume $10.7M, 12,271 trades in 24h, 406 trades in
  the last hour (after the US close); AAPLc/USDC
  0xF5FCB9CDAFcE67d50AfEf298F88E709d2B946BA6, liquidity $0.42M, 24h volume
  $3.6M, 113 trades in the last hour; TSLAc/USDC
  0x7A33000372f3F028f074182CCb9d16cBEEfBF920, liquidity $0.51M, 24h volume
  $5.6M, 216 trades in the last hour. The v1 note saying overnight B20
  trading was thin was wrong. It is corrected here and in the app.
- **The countdown** to 9:30 AM America/New_York, computed live in the
  browser.

Still mock, labelled DEMO on screen:

- The "Ring the bell" demo open is the overnight price plus a small wobble.
  It is NOT a real open.
- The replay prediction uses a fixed 60% rule. It is a demo rule, not a
  model.

## Accuracy over real mornings

The 60% rule was scored against all 64 real mornings per stock
(2026-08-18 to 2026-11-16, 192 mornings total). Score = 100 minus 40
points per percentage point of error.

| Stock | Mornings | Avg score | Median | Avg \|gap\| | Max \|gap\| |
|-------|----------|-----------|--------|-----------|-----------|
| NVDA  | 64 | 75.7 / 100 | 82 | 1.64% | 13.08% |
| AAPL  | 64 | 89.9 / 100 | 93 | 0.64% | 3.77% |
| TSLA  | 64 | 80.0 / 100 | 83 | 1.25% | 4.69% |
| All three | 192 | 81.8 / 100 | — | — | — |

Honest reading: this scores the rule, not the gauge. The rule predicts
60% of the actual move, so its score mostly measures how big the gaps
were. Small-gap mornings score high by construction. The overnight
gauge's real predictive skill can only be scored once overnight Base
prices are logged night after night and compared with the next open.
That nightly log is now running, see below. Worst single
morning for the rule: NVDA 2026-11-13, real gap +4.34%, rule predicts
+2.60%, score 31/100.

## Nightly log

Started 2026-11-17. Every weekday, just before the 9:30 AM ET open, the
log captures the live Aerodrome DexScreener price, the Chainlink NAV and
the previous close for NVDA, AAPL and TSLA. After the open it scores
that capture against the real Yahoo Finance open.

- Script: `nightly_log.py` — `capture` and `score` modes. Run
  `python3 nightly_log.py capture` or `python3 nightly_log.py score`.
  Score = max(0, 100 - abs(predicted gap - actual gap) * 40).
- Log file: `nightly_log.jsonl` — one JSON line per stock per capture,
  one score line per stock per morning. No price is ever invented: a
  failed fetch skips that stock and is logged, weekends are skipped, and
  a capture already logged for a date is not duplicated.
- Summary: `nightly_log_summary.md` — running count, average, best and
  worst morning, refreshed by every score run.
- Schedule (silent, no chat message unless a mode fails 3 times in a
  row): cron `prebell-nightly-capture`, weekdays ~15:15 WAT (9:15 ET);
  cron `prebell-morning-score`, weekdays ~17:00 WAT (11:00 ET). Both
  owned by the Base Stocks Maxxing goal.
- First capture, 2026-11-17 09:59:47 WAT (03:59 ET, before the open),
  for the 2026-11-17 open: NVDA DEX $157.47, gap +0.85%, NAV $157.15
  (2h 56m old); AAPL DEX $351.72, gap -0.30%, NAV $352.29 (40m old);
  TSLA DEX $377.52, gap -0.58%, NAV $379.07 (3h 18m old). Previous
  closes (2026-11-16): NVDA $156.14, AAPL $352.78, TSLA $379.74.
  Scoring for this morning runs after the open; the dry-run test of the
  scoring math against 2026-11-16 gave NVDA 29, AAPL 53, TSLA 16 on a
  late snapshot prediction, which is a test artifact, not a gauge result.

## Honest limits

- The Chainlink NAV is a reference value, not a trade price. It is price
  times the token multiplier, it only updates on a 0.5% move or a 24-hour
  heartbeat, and it can be hours old. At snapshot time the AAPL NAV was
  3 hours 24 minutes old, while the DEX price was seconds old. The gauge
  uses the DEX trade price, not the NAV. The app flags NAV older than 60
  minutes as STALE.
- DEX price and NAV differ by design. NVDA NAV $156.31 vs DEX $156.14 is
  the multiplier at work (1.0005379). AAPL NAV $351.96 vs DEX $352.96
  differs by 0.28%: the NAV is a total-return value, the DEX price is
  what the token actually trades for.
- A third-party API (Ozmium) lists the same B20 data behind an x402
  paywall. It was not used: no payment allowed.
- The Coinbase Tokenized Stocks API base URL is
  `https://api.coinbase.com/v1/tokenized-stocks`. It is not printed as a
  base URL in the docs overview; it was found in the docs page source.
- This is not investment advice. Pre-Bell predicts a gap, it does not
  tell anyone to buy or sell.
- The app does not enable trading for US users. It only shows prices and
  a gap. No trade is placed anywhere.

## Re-fetching the snapshot

```
python3 fetch_real.py   # pulls all four sources, writes real_data.json
python3 build.py        # injects the snapshot into index.html
node server.js          # serve on http://localhost:4194
```

`GET /api/prices` returns live prices (60s cache) or the labelled
snapshot on failure. `GET /api/snapshot` returns the snapshot as stored.

## What is next for a real entry

- Keep the nightly log running; after a few mornings the summary gives
  the gauge's real accuracy number, which is the traction story.
- Ship the demo early and post daily, because traction is half the score.
- Submission, when ready: public X video demo tagging @buildonbase, then
  the Google Form. Not done here.

## Honest grades for this build, as built

- mind-blowing: partly. The countdown plus the accuracy reveal is a real
  moment, but a gauge is not mind-blowing.
- captivating: yes. The ticking countdown and the live gauge hold attention.
- fantastic: partly. The overnight feed is now real, but the prediction is
  still a fixed rule, not a model.
- wow: yes. The bell reveal, with the score snapping in, is the wow.
- unique: yes. An overnight opening-gap gauge for Base tokenized stocks is
  a fresh angle.
- original: partly. Gap prediction is an old idea. The 24/7 Base framing
  is the new part.

## Files

- `index.html` — the whole app, no dependencies (built from
  `index.template.html` + `real_data.json`).
- `index.template.html` — the app source, with a `__SNAPSHOT_JSON__`
  placeholder.
- `real_data.json` — the snapshot: B20 records, NAVs, Chainlink values,
  DEX pools, 65 days of history, 64 scored mornings per stock.
- `fetch_real.py` — re-fetches all four public sources.
- `build.py` — injects the snapshot into `index.html`.
- `server.js` — tiny local server, port 4194, plus `/api/prices` and
  `/api/snapshot`.
- `nightly_log.py` — nightly log, `capture` and `score` modes.
- `nightly_log.jsonl` — the log: one capture line per stock per morning,
  one score line per stock per morning.
- `nightly_log_summary.md` — running accuracy summary, refreshed by
  every score run.
- `nightly_log_failures.json` — consecutive failure counts per mode
  (resets on success; the crons only message Eddie at 3 in a row).
- `LICENSE` — MIT.

## Test log (v2, 2026-11-16)

- `node --check` on server.js and on the inline app script: both pass.
- `GET /` returns HTTP 200, 58,240 bytes.
- `GET /api/prices` returns live:true at 22:50:09Z: NVDA DEX $156.075
  (gap -0.04%), AAPL $352.96 (+0.05%), TSLA $378.77 (-0.26%), NAVs
  present for all three and equal to the Chainlink values.
- Headless Chrome render: badge reads "LIVE - REAL BASE PRICES", live
  price $156.07, gap -0.04%, countdown ticking (15:38:50 at test time),
  summary table shows 192 mornings, 81.8 / 100. Test server stopped
  afterwards.
- Note: the browser-direct DexScreener call did not complete inside
  headless Chrome (no proxy there), so the app now tries `/api/prices`
  first and DexScreener second, snapshot last. The LIVE badge in the
  render above came through `/api/prices`.

## Test log (nightly log, 2026-11-17)

- Score dry-run against 2026-11-16 using a temp log with snapshot
  captures: NVDA pred -4.12% vs actual -2.35% = 29, AAPL pred -0.93%
  vs actual +0.24% = 53, TSLA pred -2.94% vs actual -0.83% = 16.
  Scoring math proven; temp log unchanged (3 lines, no score lines).
- First live capture, 2026-11-17 09:59:47 WAT for the 2026-11-17 open:
  NVDA $157.47 (+0.85%), AAPL $351.72 (-0.30%), TSLA $377.52 (-0.58%),
  all 3 written, 0 failed. Values move sensibly vs the 2026-11-16
  22:50 UTC snapshot (NVDA $156.07, AAPL $352.96, TSLA $378.77).
- Re-running capture immediately after writes nothing (0 written, 3
  already present): idempotency proven, so a cron retry cannot double-log.
- NAV ages at first capture: NVDA 2h 56m, AAPL 40m, TSLA 3h 18m —
  Chainlink only updates on a 0.5% move or a 24h heartbeat, as expected.
