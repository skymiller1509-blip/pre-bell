// Pre-Bell local server. Static files + a live price proxy.
// Run: node server.js   then open http://localhost:4194
// GET /api/prices returns live DexScreener prices, Coinbase NAVs and
// Chainlink feed values for NVDA/AAPL/TSLA, cached 60s. On any live
// failure it returns the labelled snapshot from real_data.json.
// No wallet, no login, no contract writes, no trades. Read-only.
const http = require("http");
const fs = require("fs");
const path = require("path");
const PORT = 4194;
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".md": "text/plain", ".json": "application/json" };
const SNAPSHOT = JSON.parse(fs.readFileSync(path.join(__dirname, "real_data.json"), "utf8"));

const FEEDS = {
  NVDA: "0x04689a41629776563E6822F76f2e57D148d28513",
  AAPL: "0x787f13dEa48Db0897CbCDD985de77809D837F988",
  TSLA: "0xFaf869185383a24F8cb00e27BdA6b63B9905DCb4",
};
const B20 = { NVDA: "NVDAc", AAPL: "AAPLc", TSLA: "TSLAc" };

let cache = null, cacheAt = 0;

async function ethCall(to, data) {
  const r = await fetch("https://mainnet.base.org", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_call", params: [{ to, data }, "latest"] }),
  });
  const j = await r.json();
  return j.result; // 0x + 5x32 bytes
}

function parseLatestRoundData(hex) {
  const b = Buffer.from(hex.slice(2), "hex");
  const answer = BigInt.asIntN(256, BigInt("0x" + b.subarray(32, 64).toString("hex")));
  const updated = Number(BigInt("0x" + b.subarray(96, 128).toString("hex")));
  return { price: Number(answer) / 1e8, updatedAt: updated };
}

async function livePrices() {
  const now = Date.now();
  if (cache && now - cacheAt < 60000) return cache;
  const out = { live: true, fetched_at_utc: new Date().toISOString().replace(/\.\d+Z$/, "Z"), stocks: {} };
  const dex = await Promise.all(Object.values(B20).map(async (s) => {
    const t = SNAPSHOT.stocks[Object.keys(B20).find((k) => B20[k] === s)];
    const r = await fetch("https://api.dexscreener.com/latest/dex/tokens/" + t.contract_address);
    return [s, await r.json()];
  }));
  // Paginate the Coinbase list: NVDAc/AAPLc sit on later pages (ordered by contract address).
  const api = { tokens: [] };
  let tok = null;
  for (let i = 0; i < 5; i++) {
    const r = await fetch("https://api.coinbase.com/v1/tokenized-stocks?page_size=100" + (tok ? "&page_token=" + tok : ""));
    const d = await r.json();
    api.tokens.push(...(d.tokens || []));
    tok = d.next_page_token;
    if (!tok || ["NVDAc", "AAPLc", "TSLAc"].every((s) => api.tokens.some((t) => t.symbol === s))) break;
  }
  const navBySymbol = {};
  (api.tokens || []).forEach((t) => { navBySymbol[t.symbol] = t; });
  for (const sym of Object.keys(FEEDS)) {
    const snap = SNAPSHOT.stocks[sym];
    const dexJson = dex.find(([s]) => s === B20[sym])[1];
    const pairs = (dexJson.pairs || []).filter((p) => p.dexId === "aero" && p.quoteToken.symbol === "USDC");
    pairs.sort((a, b) => (b.liquidity.usd || 0) - (a.liquidity.usd || 0));
    const top = pairs[0];
    const cl = parseLatestRoundData(await ethCall(FEEDS[sym], "0xfeaf968c"));
    const nav = navBySymbol[B20[sym]];
    out.stocks[sym] = {
      dex_price_usd: top ? parseFloat(top.priceUsd) : null,
      dex_pair: top ? top.pairAddress : null,
      dex_liquidity_usd: top ? top.liquidity.usd : null,
      dex_volume_h24_usd: top ? top.volume.h24 : null,
      dex_txns_h1: top ? top.txns.h1 : null,
      nav_price: nav ? nav.nav_price : null,
      nav_price_updated_at: nav ? nav.nav_price_updated_at : null,
      chainlink_price: cl.price,
      chainlink_updated_at: new Date(cl.updatedAt * 1000).toISOString().replace(/\.\d+Z$/, "Z"),
      last_close: snap.last_close,
      dex_gap_vs_close_pct: top ? +(((parseFloat(top.priceUsd) - snap.last_close) / snap.last_close) * 100).toFixed(2) : null,
    };
  }
  cache = out; cacheAt = now;
  return out;
}

http.createServer(async (req, res) => {
  const url = req.url.split("?")[0];
  if (url === "/api/prices") {
    try {
      const data = await livePrices();
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify(data));
    } catch (e) {
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ live: false, error: String(e && e.message || e), snapshot: SNAPSHOT }));
    }
  }
  if (url === "/api/snapshot") {
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify(SNAPSHOT));
  }
  const file = path.join(__dirname, url === "/" ? "index.html" : decodeURIComponent(url));
  if (!file.startsWith(__dirname)) { res.writeHead(403); return res.end("forbidden"); }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); return res.end("not found"); }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    res.end(data);
  });
}).listen(PORT, () => console.log("Pre-Bell prototype on http://localhost:" + PORT));
