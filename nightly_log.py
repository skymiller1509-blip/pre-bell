#!/usr/bin/env python3
"""Pre-Bell nightly log.

Two modes, both read-only (no trades, no registration, no payment):
  capture: fetch live DexScreener Aerodrome USDC price, Chainlink NAV
           (latestRoundData on Base) and the previous close for NVDA, AAPL,
           TSLA, and append one JSON line per stock to nightly_log.jsonl.
           Run just before the 9:30 AM ET open; the capture predicts that
           morning's opening gap.
  score:   for each unscored capture whose US open has passed, fetch the
           real open from Yahoo Finance, compute the actual gap vs the
           previous close, score the prediction, append a score line, and
           refresh nightly_log_summary.md.

Rules: skip weekends (no US open next day). If a fetch fails for a stock,
skip that stock and log the failure; never invent a price. Captures are
idempotent per symbol + target date (a second run does not duplicate).
A score is only written once the real open is known.

Usage:
  python3 nightly_log.py capture [--log-file PATH]
  python3 nightly_log.py score [--log-file PATH] [--target-date YYYY-MM-DD] [--dry-run]
"""
import datetime
import json
import os
import statistics
import subprocess
import sys
import urllib.request
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE, "nightly_log.jsonl")
SUMMARY_FILE = os.path.join(BASE, "nightly_log_summary.md")
FAILURE_FILE = os.path.join(BASE, "nightly_log_failures.json")
SNAPSHOT_FILE = os.path.join(BASE, "real_data.json")

CAST = "/home/hatch/workspace/foundry/bin/cast"
RPC = "https://mainnet.base.org"
FEEDS = {
    "NVDA": "0x04689a41629776563E6822F76f2e57D148d28513",
    "AAPL": "0x787f13dEa48Db0897CbCDD985de77809D837F988",
    "TSLA": "0xFaf869185383a24F8cb00e27BdA6b63B9905DCb4",
}
CONTRACTS = {
    "NVDA": "0xb20000000000000000000078ee7ce2fE4908108C",
    "AAPL": "0xb200000000000000000000C2e324d24d7eEcd1fb",
    "TSLA": "0xb2000000000000000000001e800a7f5189430cD0",
}
SYMBOLS = ["NVDA", "AAPL", "TSLA"]
NY = ZoneInfo("America/New_York")
LAGOS = ZoneInfo("Africa/Lagos")
UTC = datetime.timezone.utc


def now_utc():
    return datetime.datetime.now(UTC)


def fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_json(url, timeout=25):
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def chainlink(sym):
    out = subprocess.run(
        [CAST, "call", FEEDS[sym],
         "latestRoundData()(uint80,int256,uint256,uint256,uint80)",
         "--rpc-url", RPC],
        capture_output=True, text=True, timeout=60).stdout.strip().splitlines()
    vals = [int(x.split()[0]) for x in out if x.strip()]
    _round, answer, _started, updated, _answered = vals
    return {"price": answer / 1e8, "updated_at_epoch": updated,
            "updated_at": fmt(datetime.datetime.fromtimestamp(updated, UTC))}


def dex_price(sym):
    d = get_json(
        f"https://api.dexscreener.com/latest/dex/tokens/{CONTRACTS[sym]}")
    pairs = (d.get("pairs") or [])
    aero = [p for p in pairs
            if p.get("dexId") == "aero"
            and p.get("quoteToken", {}).get("symbol") == "USDC"]
    aero.sort(key=lambda p: (p.get("liquidity") or {}).get("usd", 0), reverse=True)
    if not aero:
        raise ValueError(f"no Aerodrome USDC pool found for {sym}")
    top = aero[0]
    return {"price_usd": float(top["priceUsd"]),
            "pair_address": top.get("pairAddress"),
            "liquidity_usd": (top.get("liquidity") or {}).get("usd"),
            "volume_h24_usd": (top.get("volume") or {}).get("h24")}


def yahoo_history(sym):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           "?range=5d&interval=1d&includePrePost=false")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=25))
    r = d["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(r["timestamp"]):
        o, c = q["open"][i], q["close"][i]
        if o is None or c is None:
            continue
        out.append({"date": datetime.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d"),
                    "open": round(o, 2), "close": round(c, 2)})
    return out


def snapshot_close(sym):
    try:
        snap = json.load(open(SNAPSHOT_FILE))
        s = snap["stocks"][sym]
        return s["last_close"], s["last_close_date"]
    except Exception:
        return None, None


def prev_close_for(sym, target_date, hist_cache):
    """Close of the last trading day before target_date, from Yahoo history."""
    hist = hist_cache.get(sym)
    if hist is None:
        try:
            hist = yahoo_history(sym)
        except Exception as e:
            print(f"  {sym}: Yahoo history failed ({e}), falling back to snapshot")
            hist = []
        hist_cache[sym] = hist
    before = [h for h in hist if h["date"] < target_date]
    if before:
        return before[-1]["close"], before[-1]["date"]
    return snapshot_close(sym)


def read_log(path):
    if not os.path.exists(path):
        return []
    lines = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"  warning: skipping unparsable log line: {line[:120]}")
    return lines


def append_log(path, entry):
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_failures():
    try:
        return json.load(open(FAILURE_FILE))
    except Exception:
        return {"capture": 0, "score": 0}


def save_failures(state):
    json.dump(state, open(FAILURE_FILE, "w"), indent=1)


def next_weekday(d):
    d += datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    return d


def prev_weekday(d):
    d -= datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d


def capture_target_date(now_ny):
    """The US trading day this capture predicts. None on weekends."""
    if now_ny.weekday() >= 5:
        return None
    if now_ny.hour < 9 or (now_ny.hour == 9 and now_ny.minute < 30):
        return now_ny.date()
    return next_weekday(now_ny.date())


def do_capture(log_file):
    now = now_utc()
    now_ny = now.astimezone(NY)
    target = capture_target_date(now_ny)
    if target is None:
        print(f"weekend ({now_ny.date()}), no US open to predict; skipping capture")
        return 0
    target_s = target.isoformat()
    print(f"capture for open {target_s} (now {fmt(now)} UTC / "
          f"{fmt(now.astimezone(LAGOS))} WAT / {now_ny.strftime('%H:%M')} ET)")
    existing = {(e.get("symbol"), e.get("target_date"))
                for e in read_log(log_file) if e.get("kind") == "capture"}
    failures = load_failures()
    wrote, skipped, failed = 0, 0, 0
    hist_cache = {}
    for sym in SYMBOLS:
        if (sym, target_s) in existing:
            print(f"  {sym}: capture already logged for {target_s}; skipping duplicate")
            skipped += 1
            continue
        try:
            dex = dex_price(sym)
            cl = chainlink(sym)
            prev_close, prev_date = prev_close_for(sym, target_s, hist_cache)
            if prev_close is None:
                raise ValueError("no previous close available")
            gap = round((dex["price_usd"] - prev_close) / prev_close * 100, 2)
            nav_age = int(now.timestamp()) - cl["updated_at_epoch"]
            entry = {
                "kind": "capture", "symbol": sym, "target_date": target_s,
                "prev_close": prev_close, "prev_close_date": prev_date,
                "captured_at_utc": fmt(now),
                "captured_at_wat": fmt(now.astimezone(LAGOS)),
                "dex_price": dex["price_usd"],
                "dex_pair": dex["pair_address"],
                "dex_liquidity_usd": dex["liquidity_usd"],
                "dex_volume_h24_usd": dex["volume_h24_usd"],
                "dex_gap_vs_close_pct": gap,
                "nav_price": cl["price"],
                "nav_updated_at": cl["updated_at"],
                "nav_age_seconds": nav_age,
            }
            append_log(log_file, entry)
            print(f"  {sym}: dex ${dex['price_usd']} gap {gap:+.2f}% "
                  f"NAV ${cl['price']} (age {nav_age}s) prev close ${prev_close} ({prev_date})")
            wrote += 1
        except Exception as e:
            print(f"  {sym}: FAILED ({e}); no price invented, stock skipped")
            failed += 1
    if failed:
        failures["capture"] = failures.get("capture", 0) + 1
        failures["last_failure"] = fmt(now)
        failures["last_failure_mode"] = "capture"
    else:
        failures["capture"] = 0
    save_failures(failures)
    print(f"capture done: {wrote} written, {skipped} already present, {failed} failed")
    return 1 if failed and wrote == 0 else 0


def score_value(pred_gap, actual_gap):
    err = abs(pred_gap - actual_gap)
    return max(0, round(100 - err * 40)), round(err, 2)


def do_score(log_file, target_date=None, dry_run=False):
    now = now_utc()
    now_ny = now.astimezone(NY)
    entries = read_log(log_file)
    captures = [e for e in entries if e.get("kind") == "capture"]
    scored_keys = {(e.get("symbol"), e.get("target_date"))
                   for e in entries if e.get("kind") == "score"}
    if target_date:
        due = [c for c in captures
               if c.get("target_date") == target_date
               and (c.get("symbol"), c.get("target_date")) not in scored_keys]
    else:
        # Every unscored capture whose 9:30 ET open has passed.
        due = []
        for c in captures:
            key = (c.get("symbol"), c.get("target_date"))
            if key in scored_keys:
                continue
            td = datetime.date.fromisoformat(c["target_date"])
            open_dt = datetime.datetime.combine(td, datetime.time(9, 30), NY)
            if now >= open_dt.astimezone(UTC):
                due.append(c)
    if not due:
        print("nothing to score: no unscored capture whose open has passed")
        return 0
    failures = load_failures()
    hist_cache = {}
    scored, failed = 0, 0
    for cap in sorted(due, key=lambda c: (c["target_date"], c["symbol"])):
        sym, td = cap["symbol"], cap["target_date"]
        try:
            hist = hist_cache.get(sym)
            if hist is None:
                hist = yahoo_history(sym)
                hist_cache[sym] = hist
            day = next((h for h in hist if h["date"] == td), None)
            if day is None:
                print(f"  {sym} {td}: no Yahoo open yet (holiday or data not published); leaving unscored")
                failed += 1
                continue
            actual = round((day["open"] - cap["prev_close"]) / cap["prev_close"] * 100, 2)
            score, err = score_value(cap["dex_gap_vs_close_pct"], actual)
            entry = {
                "kind": "score", "symbol": sym, "target_date": td,
                "prev_close": cap["prev_close"], "open": day["open"],
                "pred_gap_pct": cap["dex_gap_vs_close_pct"],
                "actual_gap_pct": actual, "error_pts": err, "score": score,
                "captured_at_utc": cap.get("captured_at_utc"),
                "scored_at_utc": fmt(now), "scored_at_wat": fmt(now.astimezone(LAGOS)),
            }
            print(f"  {sym} {td}: pred {entry['pred_gap_pct']:+.2f}% actual {actual:+.2f}% "
                  f"open ${day['open']} score {score}/100")
            if not dry_run:
                append_log(log_file, entry)
            scored += 1
        except Exception as e:
            print(f"  {sym} {td}: FAILED ({e}); leaving unscored")
            failed += 1
    if not dry_run:
        if failed:
            failures["score"] = failures.get("score", 0) + 1
            failures["last_failure"] = fmt(now)
            failures["last_failure_mode"] = "score"
        else:
            failures["score"] = 0
        save_failures(failures)
        if scored:
            update_summary(log_file)
    print(f"score done: {scored} scored, {failed} failed/skipped"
          + (" (dry run, nothing written)" if dry_run else ""))
    return 1 if failed and scored == 0 else 0


def update_summary(log_file):
    entries = read_log(log_file)
    scores = [e for e in entries if e.get("kind") == "score"]
    lines = ["# Pre-Bell nightly log summary\n",
             "Running accuracy of the overnight Base price prediction against the real US open.\n",
             f"Updated {fmt(now_utc())} UTC.\n"]
    if not scores:
        lines.append("\nNo mornings scored yet.\n")
    else:
        all_scores = [e["score"] for e in scores]
        lines.append(f"\nOverall: {len(scores)} mornings scored, "
                     f"average {statistics.mean(all_scores):.1f}/100, "
                     f"median {statistics.median(all_scores):.0f}, "
                     f"best {max(all_scores)}, worst {min(all_scores)}.\n")
        for sym in SYMBOLS:
            ss = [e["score"] for e in scores if e["symbol"] == sym]
            if ss:
                lines.append(f"- {sym}: {len(ss)} mornings, average "
                             f"{statistics.mean(ss):.1f}/100, best {max(ss)}, worst {min(ss)}.\n")
        lines.append("\n## Latest mornings\n\n")
        lines.append("| Date | Stock | Pred gap | Actual gap | Score |\n")
        lines.append("|---|---|---|---|---|\n")
        for e in sorted(scores, key=lambda x: (x["target_date"], x["symbol"]))[-15:]:
            lines.append(f"| {e['target_date']} | {e['symbol']} | "
                         f"{e['pred_gap_pct']:+.2f}% | {e['actual_gap_pct']:+.2f}% | {e['score']} |\n")
        lines.append("\nHonest note: this scores the overnight DexScreener price as the "
                     "prediction. It is the gauge's real predictive skill, night by night, "
                     "not the old 60% demo rule.\n")
    with open(SUMMARY_FILE, "w") as f:
        f.writelines(lines)
    print(f"summary updated: {SUMMARY_FILE} ({len(scores)} mornings)")


def main(argv):
    if len(argv) < 2 or argv[1] not in ("capture", "score"):
        print(__doc__)
        return 2
    log_file = LOG_FILE
    target_date = None
    dry_run = False
    i = 2
    while i < len(argv):
        if argv[i] == "--log-file" and i + 1 < len(argv):
            log_file = argv[i + 1]
            i += 2
        elif argv[i] == "--target-date" and i + 1 < len(argv):
            target_date = argv[i + 1]
            i += 2
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            print(f"unknown argument: {argv[i]}")
            return 2
    if argv[1] == "capture":
        return do_capture(log_file)
    return do_score(log_file, target_date=target_date, dry_run=dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
