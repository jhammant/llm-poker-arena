"""poker-arena: a read-only web viewer for the LLM poker bake-off results.

Deployed on Loom (runtime: python -> containerized), so it can't see the host's
runs/ dir. Instead a tiny host-side loop POSTs each checkpoint to /ingest (token
protected) and we serve the latest pushed snapshot. Stdlib only; runs no games.
"""
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORT = int(os.environ.get("PORT", 3000))
TOKEN = os.environ.get("POKER_INGEST_TOKEN", "pokerllm-local-push")
DATA_FILE = os.environ.get("POKER_DATA_FILE", "/tmp/poker_latest.json")
LIVE_FILE = os.environ.get("POKER_LIVE_FILE", "/tmp/poker_live.json")
# Fallbacks for local testing (read straight from the project runs dir).
LOCAL_FALLBACK = os.environ.get("POKER_RUNS_FILE", "/Users/jhammant/dev/PokerTest/runs/overnight_local.json")
LOCAL_LIVE = os.environ.get("POKER_LIVE_FALLBACK", "/Users/jhammant/dev/PokerTest/runs/live_table.json")

_HERE = os.path.dirname(os.path.abspath(__file__))
try:
    with open(os.path.join(_HERE, "show.html")) as _f:
        SHOW_PAGE = _f.read()
except FileNotFoundError:
    SHOW_PAGE = "<h1>show.html missing</h1>"


def _load(*paths):
    for path in paths:
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            continue
    return None


def load_results():
    return _load(DATA_FILE, LOCAL_FALLBACK)


def load_live():
    return _load(LIVE_FILE, LOCAL_LIVE)


try:
    import loom_sdk  # provided when deployed on Loom with `consumes: [analytics]`
except Exception:
    loom_sdk = None


def track_view(path):
    if loom_sdk is None:
        return
    try:
        loom_sdk.analytics().track("page_view", {"path": path})  # fire-and-forget
    except Exception:
        pass


def view_stats():
    if loom_sdk is None:
        return {"analytics": "not configured (run on Loom for stats)"}
    try:
        return loom_sdk.analytics().stats()
    except Exception as e:
        return {"error": str(e)}


def find_match(matches, x, y):
    for m in matches:
        if m["a"] == x and m["b"] == y:
            return m["chips_a"]
        if m["a"] == y and m["b"] == x:
            return -m["chips_a"]
    return None


def esc(s):
    return html.escape(str(s))


CSS = """
:root{--bg:#0c1018;--panel:#141b27;--line:#26303f;--text:#e8eef6;--muted:#8aa0b8;
--gold:#e7b94e;--red:#ef5d6c;--green:#3fd18b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:24px}
h1{font-size:22px;margin:0 0 4px}h1 span{color:var(--gold)}
h2{font-size:15px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;
margin:28px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
.sub{color:var(--muted);font-size:13px;margin-bottom:6px}
.badge{display:inline-block;font-weight:700;border-radius:20px;padding:2px 10px;font-size:12px}
.run{background:#1b2433;color:var(--gold)}.done{background:#10341f;color:var(--green)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.pos{color:var(--green)}.neg{color:var(--red)}
.tag{font-size:10px;background:#3a2e12;color:var(--gold);border-radius:6px;padding:1px 6px;margin-left:6px}
.foot{color:var(--muted);font-size:12px;margin-top:24px}
.verd-good{color:var(--green)}.verd-bad{color:var(--red)}.verd-mid{color:var(--muted)}
"""


def render(results):
    cfg = results.get("config", {})
    ratings = results.get("ratings", [])
    matches = results.get("matches", [])
    status = cfg.get("status", "complete")
    parts = []
    a = parts.append

    a("<!doctype html><html><head><meta charset='utf-8'>")
    a("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    if status == "running":
        a("<meta http-equiv='refresh' content='15'>")
    a(f"<title>LLM Poker Arena — leaderboard</title><style>{CSS}</style></head><body><div class='wrap'>")

    a("<h1><span>&#9824; LLM Poker Arena</span> — leaderboard</h1>")
    badge = ("<span class='badge run'>&#128993; LIVE (updates every 15s)</span>" if status == "running"
             else "<span class='badge done'>&#128994; complete</span>")
    a(f"<div class='sub'>{badge} &nbsp; {len(matches)} matches &nbsp;·&nbsp; updated {esc(results.get('created',''))}</div>")
    a(f"<div class='sub'>Heads-up NLHE · {cfg.get('hands','?')} hands/match · "
      f"duplicate {'on' if cfg.get('duplicate') else 'off'} · "
      f"tuition: {esc(cfg.get('tuition_mode','-'))} ({cfg.get('tuition_chars',0)} chars)</div>")

    a("<h2>Leaderboard</h2><table><tr><th>#</th><th>Competitor</th><th class='n'>Elo</th>"
      "<th class='n'>BB/100</th><th class='n'>95% CI</th><th class='n'>Hands</th></tr>")
    rows = sorted(ratings, key=lambda r: (1 if r["hands"] > 0 else 0, r["elo"]), reverse=True)
    rank = 0
    for r in rows:
        played = r["hands"] > 0
        rank += 1 if played else 0
        ci = f"[{r['ci'][0]:+.0f}, {r['ci'][1]:+.0f}]" if played else "—"
        cls = "pos" if r["bb100"] >= 0 else "neg"
        tui = "<span class='tag'>tuition</span>" if r["tuition"] else ""
        bb = f"<span class='{cls}'>{r['bb100']:+.1f}</span>" if played else "<span class='verd-mid'>queued</span>"
        a(f"<tr><td>{rank if played else '·'}</td><td>{esc(r['label'])}{tui}</td>"
          f"<td class='n'>{r['elo']:.0f}</td><td class='n'>{bb}</td>"
          f"<td class='n'>{esc(ci)}</td><td class='n'>{r['hands']}</td></tr>")
    a("</table>")

    by_model = {}
    for r in ratings:
        by_model.setdefault(r["model"], {})["tuition" if r["tuition"] else "plain"] = r
    paired = {m: v for m, v in by_model.items() if "plain" in v and "tuition" in v}
    if paired:
        a("<h2>Does tuition help? (same model &#177; strategy docs)</h2>")
        a("<table><tr><th>Model</th><th class='n'>BB/100 plain</th><th class='n'>BB/100 +docs</th>"
          "<th class='n'>&#916;</th><th class='n'>Head-to-head</th><th>Verdict</th></tr>")
        for model, v in paired.items():
            p, t = v["plain"], v["tuition"]
            chips = find_match(matches, t["label"], p["label"])
            if t["hands"] == 0 or p["hands"] == 0 or chips is None:
                verdict, vcls, h2h = "not yet played", "verd-mid", "—"
            else:
                h2h = f"{chips:+d}"
                if chips > 0:
                    verdict, vcls = "tuition helped", "verd-good"
                elif chips < 0:
                    verdict, vcls = "tuition hurt", "verd-bad"
                else:
                    verdict, vcls = "level", "verd-mid"
            a(f"<tr><td>{esc(model)}</td><td class='n'>{p['bb100']:+.1f}</td>"
              f"<td class='n'>{t['bb100']:+.1f}</td><td class='n'>{(t['bb100']-p['bb100']):+.1f}</td>"
              f"<td class='n'>{esc(h2h)}</td><td class='{vcls}'>{verdict}</td></tr>")
        a("</table>")

    if matches:
        a("<h2>Match results</h2><table><tr><th>A</th><th>B</th><th class='n'>A chips</th>"
          "<th class='n'>A BB/100</th><th class='n'>Time</th></tr>")
        for m in matches:
            a(f"<tr><td>{esc(m['a'])}</td><td>{esc(m['b'])}</td><td class='n'>{m['chips_a']:+d}</td>"
              f"<td class='n'>{m['bb100_a']:+.1f}</td><td class='n'>{m['seconds']:.0f}s</td></tr>")
        a("</table>")

    a("<div class='foot'>Read-only viewer · poker is high-variance, trust a BB/100 only when its "
      "CI excludes 0 · hosted on Loom.</div></div></body></html>")
    return "".join(parts)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/ingest", "/ingest_live"):
            return self._send(404, json.dumps({"error": "not found"}), "application/json")
        if self.headers.get("X-Token", "") != TOKEN:
            return self._send(403, json.dumps({"error": "bad token"}), "application/json")
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            data = json.loads(raw)
        except Exception as e:
            return self._send(400, json.dumps({"error": f"invalid json: {e}"}), "application/json")
        target = LIVE_FILE if path == "/ingest_live" else DATA_FILE
        with open(target, "w") as f:
            json.dump(data, f)
        return self._send(200, json.dumps({"status": "ok"}), "application/json")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self._send(200, json.dumps({"status": "ok"}), "application/json")
        if path == "/api/live":
            live = load_live()
            return self._send(200, json.dumps(live or {}), "application/json")
        if path == "/api/results":
            return self._send(200, json.dumps(load_results() or {}), "application/json")
        if path == "/api/stats":  # loom analytics: page-view stats
            return self._send(200, json.dumps(view_stats()), "application/json")
        if path == "/board":  # plain leaderboard page
            track_view("/board")
            results = load_results()
            if results is None:
                return self._send(200, "<h1>No results yet</h1>")
            return self._send(200, render(results))
        # default: the live broadcast page (it fetches /api/live + /api/results)
        track_view("/")
        return self._send(200, SHOW_PAGE)


if __name__ == "__main__":
    print(f"[poker-arena] :{PORT} (data file {DATA_FILE})")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
