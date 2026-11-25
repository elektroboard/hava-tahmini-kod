"""Paneldeki sayfayı (web/index.html) verileri içine gömülü, tek başına açılan bir HTML dosyasına çevirir.

Panelin sağladığı `dash` altyapısının (veri, çizim, filtre) küçük bir benzeri dosyanın içine konur;
sayfa kodu panelle birebir aynıdır. Çıktı: Tahmin_Masasi.html (proje klasöründe).

Kullanım: python html_rapor.py
"""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

KLASOR = Path(__file__).parent
WEB = KLASOR / "web"
CIKTI = KLASOR / "Tahmin_Masasi.html"

TEMA = """
<style>
  :root {
    --color-bg: #f6f7f9; --color-panel: #ffffff; --color-fg: #1c2330; --color-fg-muted: #5f6b7a;
    --color-border-line: #dde2e8; --color-ok: #1f8a4c; --color-warn: #e0a106; --color-bad: #c8382d;
    --font-anthropic-sans: "Segoe UI", system-ui, -apple-system, Roboto, sans-serif;
    --font-anthropic-serif: Georgia, "Times New Roman", serif;
    --cds-font-size-caption: 12.5px; --cds-font-size-body: 15px; --cds-font-size-heading: 18px; --cds-font-size-title: 28px;
    --cds-font-weight-medium: 600;
    --cds-gap-xs: 6px; --cds-gap-sm: 10px; --cds-gap-md: 14px; --cds-gap-lg: 20px; --cds-gap-xl: 32px;
    --cds-pad-xs: 4px; --cds-pad-sm: 10px; --cds-pad-md: 14px; --cds-pad-lg: 20px; --cds-pad-xl: 28px;
    --cds-radius: 12px;
    --cds-chart-muted: #b9c1cc; --cds-chart-grid: #e6e9ee; --cds-chart-axis: #c4cad3; --cds-chart-reference: #8a94a3;
    --cds-text-secondary: #5f6b7a; --cds-surface-popover: #ffffff; --cds-border: #dde2e8;
    --cds-shadow-popover: 0 6px 24px rgba(20, 30, 45, .14);
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --color-bg: #111418; --color-panel: #1a1f25; --color-fg: #e8ecf1; --color-fg-muted: #9aa5b3;
      --color-border-line: #2c333c; --color-ok: #4cc283; --color-warn: #f2be3c; --color-bad: #ef6b60;
      --cds-chart-muted: #4a535f; --cds-chart-grid: #262c34; --cds-chart-axis: #3a424d; --cds-chart-reference: #8a94a3;
      --cds-text-secondary: #9aa5b3; --cds-surface-popover: #222830; --cds-border: #353d47;
      --cds-shadow-popover: 0 6px 24px rgba(0, 0, 0, .5);
      color-scheme: dark;
    }
  }
  html, body { margin: 0; background: var(--color-bg); color: var(--color-fg); font-family: var(--font-anthropic-sans); font-size: var(--cds-font-size-body); line-height: 1.4; }
  #dash-root { max-width: 1080px; margin: 0 auto; padding: 24px max(16px, env(safe-area-inset-right, 0px)) 48px max(16px, env(safe-area-inset-left, 0px)); }
  [hidden] { display: none !important; }
  .dash-skeleton { color: transparent !important; background: var(--color-border-line); border-radius: 6px; min-width: 3em; min-height: 1em; display: inline-block; }
  .atm-dosya-not { font-size: var(--cds-font-size-caption); color: var(--color-fg-muted); margin-top: var(--cds-gap-xl); }
</style>
"""

SHIM = """
<script>
  // Panelin `dash` altyapısının dosya içi benzeri: veriler ATM_VERI'den okunur.
  window.dash = (function () {
    const V = window.ATM_VERI;
    let params = {};
    const h = (location.hash || "").slice(1);
    if (h) params.sehir = h;
    const cizimler = [], dinleyiciler = [], hesaplar = {};
    const renkler = ["#3b82f6", "#f97316", "#16a34a", "#a855f7"];
    function data(id) {
      if (hesaplar[id]) {
        const c = hesaplar[id];
        try { return { status: "ok", data: c.fn(...c.inputs.map((i) => V[i] || [])) }; }
        catch (e) { console.error(e); return { status: "error", data: null, message: String(e) }; }
      }
      if (!V[id]) return { status: "missing", data: [] };
      return { status: "ok", data: V[id], columns: V[id].length ? Object.keys(V[id][0]) : [] };
    }
    function ciz() {
      dinleyiciler.forEach((f) => { try { f(); } catch (e) { console.error(e); } });
      for (const [ad, fn] of cizimler) {
        document.querySelectorAll('[data-draw="' + ad + '"]').forEach((el) => {
          if (el.closest("[hidden]")) return;
          try { fn(el); } catch (e) { console.error(ad, e); }
        });
      }
    }
    let bekleyen = null;
    const yeniden = () => { clearTimeout(bekleyen); bekleyen = setTimeout(ciz, 30); };
    window.addEventListener("resize", yeniden);
    window.addEventListener("DOMContentLoaded", ciz);
    return {
      data, colors: renkler,
      draw(ad, fn) { if (typeof fn === "function") cizimler.push([ad, fn]); else yeniden(); },
      calc(id, o) { hesaplar[id] = o; },
      loader() {},
      onData(fn) { dinleyiciler.push(fn); },
      params: () => ({ ...params }),
      setParams(p) {
        for (const [k, v] of Object.entries(p)) { if (v === null || v === undefined) delete params[k]; else params[k] = v; }
        ciz(); setTimeout(ciz, 0);
      },
      resetParams() { params = {}; ciz(); },
      setLink(ad) { try { history.replaceState(null, "", "#" + ad); } catch (e) {} },
      refresh() {},
    };
  })();
</script>
"""


def main():
    sayfa = (WEB / "index.html").read_text(encoding="utf-8")
    veri = {ad: json.loads((WEB / f"{ad}.json").read_text(encoding="utf-8")) for ad in ("ileri", "karne", "iklim", "test")}
    g = pd.read_csv(WEB / "gecmis.csv", dtype={"tarih": str})
    veri["gecmis"] = json.loads(g.to_json(orient="records", force_ascii=False))
    gomulu = json.dumps(veri, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    olusturma = datetime.now().strftime("%d.%m.%Y %H:%M")
    html = f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Tahmin Masası</title>
{TEMA}
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>window.ATM_VERI = {gomulu};</script>
{SHIM}
</head>
<body>
<div id="dash-root">
{sayfa}
<p class="atm-dosya-not">Bu dosya {olusturma} tarihinde oluşturuldu. Güncel hali için günlük görevin çalışması ya da gunluk.py'nin yeniden çalıştırılması gerekir. Grafikler için internet bağlantısı gerekir (d3 kütüphanesi).</p>
</div>
</body>
</html>
"""
    CIKTI.write_text(html, encoding="utf-8")
    print(f"{CIKTI.name}: {len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
