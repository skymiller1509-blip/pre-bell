#!/usr/bin/env python3
"""Fetch real Pre-Bell data and write real_data.json.
Sources (all public, no key, no payment):
- Coinbase Tokenized Stocks API: https://api.coinbase.com/v1/tokenized-stocks
- Chainlink V3 feeds on Base, via cast eth_call to https://mainnet.base.org
- DexScreener public API: https://api.dexscreener.com/latest/dex/tokens/{address}
- Yahoo Finance chart API for daily open/close history.
Run: python3 fetch_real.py
"""
import json, subprocess, datetime, statistics, urllib.request

CAST = "/home/hatch/workspace/foundry/bin/cast"
RPC = "https://mainnet.base.org"
FEEDS = {
    "NVDA": "0x04689a41629776563E6822F76f2e57D148d28513",
    "AAPL": "0x787f13dEa48Db0897CbCDD985de77809D837F988",
    "TSLA": "0xFaf869185383a24F8cb00e27BdA6b63B9905DCb4",
}
NOW = datetime.datetime.now(datetime.timezone.utc)
FETCHED_AT = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")

def get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=25))

def chainlink(sym):
    addr = FEEDS[sym]
    out = subprocess.run([CAST, "call", addr, "latestRoundData()(uint80,int256,uint256,uint256,uint80)",
                          "--rpc-url", RPC], capture_output=True, text=True, timeout=60).stdout.strip().splitlines()
    # cast prints each return value on its own line, plain ints
    vals = [int(x.split()[0]) for x in out if x.strip()]
    round_id, answer, started, updated, answered = vals
    return {"feed": addr, "answer_raw": answer, "price": answer / 1e8,
            "updated_at_epoch": updated,
            "updated_at": datetime.datetime.fromtimestamp(updated, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

def yahoo(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d&includePrePost=false"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=25))
    r = d["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(r["timestamp"]):
        o, c = q["open"][i], q["close"][i]
        if o is None or c is None:
            continue
        out.append([datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d"),
                    round(o, 2), round(c, 2)])
    return out

def score_rule(pred_gap, actual_gap):
    err = abs(pred_gap - actual_gap)
    return max(0, round(100 - err * 40)), round(err, 2)

# --- Coinbase API, paginated ---
tokens = {}
tok = None
for _ in range(6):
    url = "https://api.coinbase.com/v1/tokenized-stocks?page_size=100" + (f"&page_token={tok}" if tok else "")
    d = get_json(url)
    for t in d.get("tokens", []):
        tokens[t["symbol"]] = t
    tok = d.get("next_page_token")
    if not tok or {"NVDAc", "AAPLc", "TSLAc"} <= set(tokens):
        break

out = {"fetched_at_utc": FETCHED_AT, "sources": {
    "b20_api": "https://api.coinbase.com/v1/tokenized-stocks (free, read-only, no key)",
    "chainlink_rpc": "https://mainnet.base.org (public RPC, latestRoundData)",
    "dex": "https://api.dexscreener.com/latest/dex/tokens/{contract} (public, CORS *)",
    "history": "https://query1.finance.yahoo.com/v8/finance/chart/{SYM}?range=3mo&interval=1d",
}, "stocks": {}}

for sym, b20 in (("NVDA", "NVDAc"), ("AAPL", "AAPLc"), ("TSLA", "TSLAc")):
    t = tokens[b20]
    cl = chainlink(sym)
    pairs = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{t['contract_address']}").get("pairs") or []
    # deepest Aerodrome Slipstream USDC pool
    aero = [p for p in pairs if p.get("dexId") == "aero" and p.get("quoteToken", {}).get("symbol") == "USDC"]
    aero.sort(key=lambda p: (p.get("liquidity") or {}).get("usd", 0), reverse=True)
    top = aero[0] if aero else None
    hist = yahoo(sym)
    close = hist[-1][2]
    dex_price = float(top["priceUsd"]) if top else None
    mornings = []
    for i in range(1, len(hist)):
        prev, op = hist[i - 1][2], hist[i][1]
        rg = (op - prev) / prev * 100
        pg = 0.6 * rg
        sc, err = score_rule(pg, rg)
        mornings.append({"date": hist[i][0], "prev_close": prev, "open": op,
                         "real_gap_pct": round(rg, 2), "rule_pred_gap_pct": round(pg, 2),
                         "rule_score": sc, "rule_error_pts": err})
    scores = [m["rule_score"] for m in mornings]
    out["stocks"][sym] = {
        "b20_symbol": b20,
        "contract_address": t["contract_address"],
        "decimals": t.get("decimals"),
        "multiplier": t.get("multiplier"),
        "total_supply_tokens": t.get("total_supply"),
        "first_mint": t.get("first_mint_date"),
        "nav_price": t.get("nav_price"),
        "nav_price_updated_at": t.get("nav_price_updated_at"),
        "chainlink": cl,
        "dex_top_pool": ({
            "dex": top.get("dexId"), "pair_address": top.get("pairAddress"),
            "pair": f"{top.get('baseToken', {}).get('symbol')}/{top.get('quoteToken', {}).get('symbol')}",
            "price_usd": float(top["priceUsd"]),
            "liquidity_usd": (top.get("liquidity") or {}).get("usd"),
            "volume_h24_usd": (top.get("volume") or {}).get("h24"),
            "volume_h6_usd": (top.get("volume") or {}).get("h6"),
            "txns_h24": (top.get("txns") or {}).get("h24"),
            "txns_h6": (top.get("txns") or {}).get("h6"),
            "txns_h1": (top.get("txns") or {}).get("h1"),
            "price_change_pct": top.get("priceChange"),
        } if top else None),
        "last_close": close,
        "last_close_date": hist[-1][0],
        "dex_gap_vs_close_pct": round((dex_price - close) / close * 100, 2) if dex_price else None,
        "nav_gap_vs_close_pct": round((t.get("nav_price") - close) / close * 100, 2) if t.get("nav_price") else None,
        "history": hist,
        "mornings_scored": len(mornings),
        "rule_avg_score": round(statistics.mean(scores), 1),
        "rule_median_score": statistics.median(scores),
        "rule_avg_abs_gap_pct": round(statistics.mean(abs(m["real_gap_pct"]) for m in mornings), 2),
        "rule_max_abs_gap_pct": max(abs(m["real_gap_pct"]) for m in mornings),
        "mornings": mornings,
    }
    s = out["stocks"][sym]
    print(sym, "NAV", s["nav_price"], "nav_at", s["nav_price_updated_at"],
          "| DEX", s["dex_top_pool"]["price_usd"], "gap", s["dex_gap_vs_close_pct"], "%",
          "| vol24 $", s["dex_top_pool"]["volume_h24_usd"], "| tx h1", s["dex_top_pool"]["txns_h1"],
          "| mornings", s["mornings_scored"], "avg score", s["rule_avg_score"])

json.dump(out, open("/home/hatch/workspace/hackathons/base-prebell/real_data.json", "w"), indent=1)
print("wrote real_data.json, fetched_at", FETCHED_AT)
