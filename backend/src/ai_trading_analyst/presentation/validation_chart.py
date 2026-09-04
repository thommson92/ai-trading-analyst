"""Der Validierungschart: Kursverlauf mit jedem Urteil der Kandidatenregel.

Er beantwortet die Frage, die keine Kennzahl beantwortet -- *sieht das
richtig aus?* Dafuer zeigt er neben den Kerzen und Indikatoren jeden
Entscheidungspunkt mit dem, was dort galt: welche Kriterien feuerten, ob eine
Torbedingung ihn verwarf, und zu welcher Episode er gehoert.

**Gerechnet wird ausschliesslich mit den Domain-Funktionen.** Eine eigene
Nachbildung der Formeln waere wertlos: Der Chart soll zeigen, was der
Screener sieht, nicht was eine zweite Implementierung daraus macht.

Die erzeugte HTML-Seite bringt alles mit -- kein CDN, keine Schriftdatei aus
dem Netz. Der Server, auf dem sie entsteht, hat kein Internet.
"""

from __future__ import annotations

import json
from typing import Any

from ai_trading_analyst.domain.backtesting import (
    find_historical_decisions,
    group_into_episodes,
    is_decision_point,
)
from ai_trading_analyst.domain.screening import (
    SIGNAL_RULE_VERSION,
    CandidateRuleParameters,
    CandleSeries,
    ScreeningStatus,
    SignalType,
    evaluate_candidate,
)

KRITERIUM_KURZ = {
    SignalType.RSI_CROSS: "RSI-Kreuz",
    SignalType.PRICE_EMA20_BREAKOUT: "Kurs kreuzt EMA20",
    SignalType.EMA5_EMA20_CROSS: "EMA5 kreuzt EMA20",
    SignalType.RSI_OVERSOLD: "RSI < 30",
    SignalType.NO_RECENT_EMA_DOWNCROSS: "kein Abwärtskreuz",
}

GRUND_KURZ = {
    "gate:stale_crossing_signals": "Signale abgelaufen",
    "gate:close_not_above_ema20": "Schluss unter EMA 20",
    "gate:stale_crossing_signals+close_not_above_ema20": (
        "Signale abgelaufen, Schluss unter EMA 20"
    ),
}


def build_chart_payload(
    symbol: str, series: CandleSeries, params: CandidateRuleParameters
) -> dict[str, Any]:
    """Alles, was die Seite braucht -- als reine Daten.

    Getrennt vom Rendern, damit sich der Inhalt pruefen laesst, ohne durch
    HTML zu lesen.
    """
    entscheidungen = find_historical_decisions(series, params)
    episoden = group_into_episodes(entscheidungen)
    episode_je_index = {
        entscheidung.index: nummer
        for nummer, episode in enumerate(episoden)
        for entscheidung in episode
    }
    erste_je_episode = {episode[0].index for episode in episoden}

    kerzen: list[dict[str, Any]] = []
    geprueft = 0
    verworfen = 0
    for i in range(len(series)):
        kerze, werte = series.candle(i), series.indicator(i)
        eintrag: dict[str, Any] = {
            "t": kerze.timestamp.isoformat(),
            "d": kerze.daily_candle_index,
            "o": round(kerze.open, 2),
            "h": round(kerze.high, 2),
            "l": round(kerze.low, 2),
            "c": round(kerze.close, 2),
            "e5": None if werte.ema5 is None else round(werte.ema5, 3),
            "e20": None if werte.ema20 is None else round(werte.ema20, 3),
            "rsi": None if werte.rsi is None else round(werte.rsi, 2),
            "rma": None if werte.rsi_ma is None else round(werte.rsi_ma, 2),
        }

        if is_decision_point(series, i):
            ergebnis = evaluate_candidate(series, i, params)
            if ergebnis.status is ScreeningStatus.CANDIDATE:
                geprueft += 1
                eintrag["sig"] = sorted(typ.value for typ in ergebnis.fired_signal_types)
                eintrag["ep"] = episode_je_index[i]
                eintrag["first"] = i in erste_je_episode
            elif ergebnis.status is ScreeningStatus.NOT_CANDIDATE:
                geprueft += 1
                if ergebnis.reason is not None:
                    verworfen += 1
                    eintrag["gate"] = ergebnis.reason
                    eintrag["sig"] = sorted(typ.value for typ in ergebnis.fired_signal_types)
        kerzen.append(eintrag)

    return {
        "symbol": symbol,
        "regelversion": SIGNAL_RULE_VERSION,
        "kerzen": kerzen,
        "geprueft": geprueft,
        "treffer": len(entscheidungen),
        "episoden": len(episoden),
        "verworfen": verworfen,
        "warmup": params.warmup_candles,
        "kriterien": {typ.value: text for typ, text in KRITERIUM_KURZ.items()},
        "gruende": dict(GRUND_KURZ),
    }


def render_chart_html(payload: dict[str, Any]) -> str:
    """Die fertige Seite -- eine Datei, ohne Abruf aus dem Netz."""
    daten = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    # Sonst beendete eine Zeichenfolge in den Daten das Skript-Element.
    daten = daten.replace("</", "<\\/")
    return _VORLAGE.replace("__DATEN__", daten)


_VORLAGE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Signalpruefung</title>
<style>
  :root {
    --ground: #eef1f6; --panel: #fff; --sunk: #f7f8fb; --line: #dfe3ec;
    --ink: #131722; --ink2: #4b5566; --ink3: #78839a;
    --bull: #0f9d76; --bear: #d94452; --ema5: #3d4350; --ema20: #4f7fd4;
    --rsi: #7c5cd6; --hit: #e09000; --hit-soft: rgba(224,144,0,.13);
    --gate: #8c93a3; --gate-soft: rgba(140,147,163,.16);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --ground: #0c0e14; --panel: #161a23; --sunk: #11141b; --line: #262c38;
      --ink: #e6e9f0; --ink2: #a3acbd; --ink3: #7a8497;
      --bull: #26b98d; --bear: #ec5a67; --ema5: #b9c0cd; --ema20: #6f9ce8;
      --rsi: #a288ea; --hit: #f2ab2e; --hit-soft: rgba(242,171,46,.16);
      --gate: #6d7585; --gate-soft: rgba(109,117,133,.2);
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--ground); color: var(--ink);
    font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  .wrap { max-width: 1600px; margin: 0 auto; padding: 24px 18px 48px;
          display: flex; flex-direction: column; gap: 18px; }
  h1 { margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -.015em; }
  .kopf { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px 14px; }
  .untertitel { color: var(--ink2); font-size: 14px; }
  .kennzahlen { display: flex; flex-wrap: wrap; gap: 9px; }
  .kennzahl { background: var(--panel); border: 1px solid var(--line); border-radius: 3px;
              padding: 8px 13px; min-width: 112px; }
  .kennzahl dt { font-size: 10.5px; text-transform: uppercase; letter-spacing: .09em;
                 color: var(--ink3); font-weight: 600; }
  .kennzahl dd { margin: 0; font: 500 19px ui-monospace, "SF Mono", Menlo, monospace;
                 font-variant-numeric: tabular-nums; }
  .kennzahl.treffer dd { color: var(--hit); }
  .steuerung { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px;
               background: var(--panel); border: 1px solid var(--line);
               border-radius: 3px; padding: 9px 13px; }
  .gruppe { display: flex; align-items: center; gap: 7px; }
  .gruppe > span { font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
                   color: var(--ink3); font-weight: 600; }
  button { font: 500 13px inherit; font-family: inherit; color: var(--ink);
           background: var(--sunk); border: 1px solid var(--line); border-radius: 3px;
           padding: 5px 11px; cursor: pointer; }
  button:hover { border-color: var(--ink3); }
  button:focus-visible { outline: 2px solid var(--ema20); outline-offset: 1px; }
  .legende { display: flex; flex-wrap: wrap; gap: 5px 15px; margin-left: auto;
             font-size: 12.5px; color: var(--ink2); }
  .legende span { display: inline-flex; align-items: center; gap: 6px; }
  .mark { width: 16px; height: 2px; border-radius: 1px; }
  .rahmen { background: var(--panel); border: 1px solid var(--line); border-radius: 3px;
            display: grid; grid-template-columns: 1fr 60px; overflow: hidden; }
  .scroll { overflow-x: auto; overflow-y: hidden; position: relative; cursor: crosshair; }
  canvas { display: block; }
  #achse { border-left: 1px solid var(--line); }
  .tip { position: absolute; z-index: 5; pointer-events: none; background: var(--panel);
         border: 1px solid var(--line); border-radius: 3px; padding: 9px 11px;
         font: 12px/1.65 ui-monospace, "SF Mono", Menlo, monospace;
         font-variant-numeric: tabular-nums; white-space: nowrap; opacity: 0;
         box-shadow: 0 6px 22px rgba(9,12,20,.16); }
  .tip.an { opacity: 1; }
  .tip .datum { font-family: inherit; font-weight: 600; display: block; margin-bottom: 3px; }
  .tip .ja { color: var(--hit); }
  .tip .nein { color: var(--ink3); }
  .hinweis { background: var(--panel); border: 1px solid var(--line);
             border-left: 3px solid var(--ema20); border-radius: 3px; padding: 13px 15px;
             font-size: 13.5px; color: var(--ink2); max-width: 78ch; }
  .hinweis p { margin: 0 0 8px; } .hinweis p:last-child { margin: 0; }
  .hinweis strong { color: var(--ink); font-weight: 600; }
</style>
</head>
<body>
<div class="wrap">
  <div>
    <div class="kopf"><h1 id="symbol"></h1><span class="untertitel" id="spanne"></span></div>
  </div>
  <dl class="kennzahlen" id="kennzahlen"></dl>
  <div class="steuerung">
    <div class="gruppe"><span>Zoom</span>
      <button type="button" data-zoom="-1" aria-label="Herauszoomen">&minus;</button>
      <button type="button" data-zoom="1" aria-label="Hineinzoomen">+</button></div>
    <div class="gruppe"><span>Springen</span>
      <button type="button" id="prev">&larr; Treffer</button>
      <button type="button" id="next">Treffer &rarr;</button>
      <button type="button" id="ende">Ende</button></div>
    <div class="legende">
      <span><i class="mark" style="background:var(--ema5)"></i>EMA 5</span>
      <span><i class="mark" style="background:var(--ema20)"></i>EMA 20</span>
      <span><i class="mark" style="background:var(--rsi)"></i>RSI 14</span>
      <span><i class="mark" style="background:var(--hit);height:9px;width:9px"></i>Kandidat</span>
      <span><i class="mark" style="background:var(--gate);height:9px;width:9px"></i>verworfen</span>
    </div>
  </div>
  <div class="rahmen">
    <div class="scroll" id="scroll" tabindex="0" role="img"
         aria-label="Kursverlauf mit Kandidaten und verworfenen Punkten">
      <canvas id="chart"></canvas><div class="tip" id="tip" role="status"></div>
    </div>
    <canvas id="achse"></canvas>
  </div>
  <div class="hinweis">
    <p><strong>Was markiert ist.</strong> Bernstein: die Regel traf zu. Ein
    ausgefuelltes Dreieck ist der <em>erste</em> Trigger einer Episode &mdash; nur
    er wird im Backtest gezaehlt; ein hohles gehoert zur selben Episode und
    zaehlt nicht noch einmal. Grau: Die Signalmenge war erfuellt, aber eine
    Torbedingung hat den Punkt verworfen; der Grund steht im Tooltip.</p>
    <p><strong>Geprueft wird nur die erste Tageskerze</strong> (12:45 ET), wie im
    Tageslauf. Die ersten Kerzen sind Vorlauf fuer die Indikatoren und werden nie
    ausgewertet.</p>
  </div>
</div>
<script id="daten" type="application/json">__DATEN__</script>
<script>
(() => {
  const D = JSON.parse(document.getElementById("daten").textContent);
  const K = D.kerzen;
  const scroll = document.getElementById("scroll");
  const cv = document.getElementById("chart"), ax = document.getElementById("achse");
  const ctx = cv.getContext("2d"), actx = ax.getContext("2d"), tip = document.getElementById("tip");
  const BREITEN = [3, 4, 6, 8, 11, 15];
  // Browser weisen jenseits von rund 65.000 Geraetepixeln kein Canvas mehr
  // zu -- die Flaeche bliebe leer, ohne dass es eine Meldung gaebe. Bei
  // einer Fuenf-Jahres-Reihe ist das ab der zweitgroessten Stufe erreicht.
  const MAX_GERAETEPIXEL = 32000;
  let zoom = 2, hoehe = 620, hover = -1;
  const RSI_ANTEIL = .26, OBEN = 14, UNTEN = 26, RSI_LUFT = 16;
  const treffer = K.map((k, i) => (k.sig && !k.gate ? i : -1)).filter(i => i >= 0);
  const F = {};
  const lies = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function farben() {
    for (const n of ["panel","sunk","line","ink","ink2","ink3","bull","bear",
                     "ema5","ema20","rsi","hit","hit-soft","gate","gate-soft"])
      F[n] = lies("--" + n);
  }
  function maxZoom() {
    const dpr = window.devicePixelRatio || 1;
    const proKerze = (MAX_GERAETEPIXEL / dpr - 40) / K.length;
    const moeglich = BREITEN.findLastIndex(b => b <= proKerze);
    return moeglich < 0 ? 0 : moeglich;
  }
  const bw = () => BREITEN[Math.min(zoom, maxZoom())];
  const breite = () => K.length * bw() + 40;
  function masse() {
    const dpr = window.devicePixelRatio || 1;
    hoehe = Math.max(440, Math.min(760, window.innerHeight - 320));
    const w = breite();
    cv.style.width = w + "px"; cv.style.height = hoehe + "px";
    cv.width = Math.round(w * dpr); cv.height = Math.round(hoehe * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ax.style.width = "60px"; ax.style.height = hoehe + "px";
    ax.width = Math.round(60 * dpr); ax.height = Math.round(hoehe * dpr);
    actx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function fenster() {
    const b = bw();
    return [Math.max(0, Math.floor((scroll.scrollLeft - 20) / b) - 1),
            Math.min(K.length - 1, Math.ceil((scroll.scrollLeft + scroll.clientWidth) / b) + 1)];
  }
  function skala(von, bis) {
    let lo = Infinity, hi = -Infinity;
    for (let i = von; i <= bis; i++) {
      const k = K[i];
      lo = Math.min(lo, k.l); hi = Math.max(hi, k.h);
      for (const v of [k.e5, k.e20]) if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    }
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    const luft = (hi - lo) * .07 || 1;
    return { lo: lo - luft, hi: hi + luft };
  }
  const preisU = () => Math.round(hoehe * (1 - RSI_ANTEIL)) - UNTEN;
  const rsiO = () => Math.round(hoehe * (1 - RSI_ANTEIL)) + RSI_LUFT;
  const yP = (v, s) => OBEN + (1 - (v - s.lo) / (s.hi - s.lo)) * (preisU() - OBEN);
  const yR = v => rsiO() + (1 - v / 100) * (hoehe - UNTEN - rsiO());
  function stufen(s) {
    const roh = (s.hi - s.lo) / 6, g = Math.pow(10, Math.floor(Math.log10(roh)));
    const schritt = [1, 2, 2.5, 5, 10].map(m => m * g).find(v => v >= roh) || g * 10;
    const out = [];
    for (let v = Math.ceil(s.lo / schritt) * schritt; v <= s.hi; v += schritt) out.push(v);
    return out;
  }
  function linie(von, bis, feld, farbe, dicke, y, s) {
    ctx.strokeStyle = farbe; ctx.lineWidth = dicke; ctx.lineJoin = "round"; ctx.beginPath();
    let offen = false;
    for (let i = von; i <= bis; i++) {
      const v = K[i][feld];
      if (v == null) { offen = false; continue; }
      const x = 20 + i * bw(), yy = y(v, s);
      offen ? ctx.lineTo(x, yy) : (ctx.moveTo(x, yy), offen = true);
    }
    ctx.stroke();
  }
  function zeichne() {
    const [von, bis] = fenster(), s = skala(von, bis), b = bw();
    const koerper = Math.max(1, b - (b > 5 ? 2 : 1));
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = F.panel; ctx.fillRect(scroll.scrollLeft, 0, scroll.clientWidth, hoehe);
    ctx.fillStyle = F.sunk;
    ctx.fillRect(scroll.scrollLeft, rsiO() - 8, scroll.clientWidth, hoehe - UNTEN - rsiO() + 8);
    ctx.strokeStyle = F.line; ctx.lineWidth = 1;
    for (const st of stufen(s)) {
      const y = Math.round(yP(st, s)) + .5;
      if (y < OBEN || y > preisU()) continue;
      ctx.beginPath(); ctx.moveTo(scroll.scrollLeft, y);
      ctx.lineTo(scroll.scrollLeft + scroll.clientWidth, y); ctx.stroke();
    }
    for (const st of [30, 50, 70]) {
      const y = Math.round(yR(st)) + .5;
      ctx.setLineDash(st === 50 ? [] : [3, 3]);
      ctx.beginPath(); ctx.moveTo(scroll.scrollLeft, y);
      ctx.lineTo(scroll.scrollLeft + scroll.clientWidth, y); ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.textBaseline = "top"; ctx.font = '500 11px ui-monospace, Menlo, monospace';
    let letzter = von > 0 ? K[von - 1].t.slice(0, 7) : "";
    for (let i = von; i <= bis; i++) {
      const m = K[i].t.slice(0, 7);
      if (m === letzter) continue;
      letzter = m;
      const x = Math.round(20 + i * b) + .5;
      ctx.strokeStyle = F.line; ctx.beginPath();
      ctx.moveTo(x, OBEN); ctx.lineTo(x, hoehe - UNTEN); ctx.stroke();
      ctx.fillStyle = F.ink3; ctx.fillText(m, x + 5, hoehe - UNTEN + 7);
    }
    for (let i = von; i <= bis; i++) {
      if (!K[i].sig) continue;
      ctx.fillStyle = K[i].gate ? F["gate-soft"] : F["hit-soft"];
      ctx.fillRect(20 + i * b - b / 2, OBEN, Math.max(b, 3), hoehe - UNTEN - OBEN);
    }
    for (let i = von; i <= bis; i++) {
      const k = K[i], x = 20 + i * b, c = k.c >= k.o ? F.bull : F.bear;
      ctx.strokeStyle = c; ctx.fillStyle = c; ctx.lineWidth = 1;
      const xm = Math.round(x) + .5;
      ctx.beginPath(); ctx.moveTo(xm, yP(k.h, s)); ctx.lineTo(xm, yP(k.l, s)); ctx.stroke();
      const yo = yP(Math.max(k.o, k.c), s), yc = yP(Math.min(k.o, k.c), s);
      ctx.fillRect(x - koerper / 2, yo, koerper, Math.max(1, yc - yo));
    }
    linie(von, bis, "e5", F.ema5, 1.5, yP, s);
    linie(von, bis, "e20", F.ema20, 1.5, yP, s);
    linie(von, bis, "rsi", F.rsi, 1.5, (v) => yR(v), s);
    linie(von, bis, "rma", F.ink2, 1.2, (v) => yR(v), s);
    for (let i = von; i <= bis; i++) {
      const k = K[i];
      if (!k.sig) continue;
      const x = 20 + i * b, y = preisU() - 2;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 5, y + 9); ctx.lineTo(x + 5, y + 9);
      ctx.closePath();
      if (k.gate) { ctx.strokeStyle = F.gate; ctx.lineWidth = 1.4; ctx.stroke(); }
      else if (k.first) { ctx.fillStyle = F.hit; ctx.fill(); }
      else { ctx.strokeStyle = F.hit; ctx.lineWidth = 1.4; ctx.stroke(); }
    }
    if (hover >= von && hover <= bis) {
      const x = Math.round(20 + hover * b) + .5;
      ctx.strokeStyle = F.ink3; ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.moveTo(x, OBEN); ctx.lineTo(x, hoehe - UNTEN); ctx.stroke();
      ctx.setLineDash([]);
    }
    actx.clearRect(0, 0, ax.width, ax.height);
    actx.fillStyle = F.panel; actx.fillRect(0, 0, 60, hoehe);
    actx.font = '400 11px ui-monospace, Menlo, monospace';
    actx.fillStyle = F.ink2; actx.textBaseline = "middle";
    for (const st of stufen(s)) {
      const y = yP(st, s);
      if (y >= OBEN && y <= preisU()) actx.fillText(st.toFixed(st >= 100 ? 0 : 1), 7, y);
    }
    actx.fillStyle = F.ink3;
    for (const st of [30, 50, 70]) actx.fillText(String(st), 7, yR(st));
  }
  const indexAus = cx => Math.round((cx - scroll.getBoundingClientRect().left
                                    + scroll.scrollLeft - 20) / bw());
  scroll.addEventListener("mousemove", e => {
    const i = indexAus(e.clientX);
    if (i < 0 || i >= K.length) { tip.classList.remove("an"); hover = -1; zeichne(); return; }
    hover = i; zeigeTip(i, e.clientX, e.clientY); zeichne();
  });
  scroll.addEventListener("mouseleave", () => {
    tip.classList.remove("an"); hover = -1; zeichne();
  });
  function zeigeTip(i, cx, cy) {
    const k = K[i], d = new Date(k.t), z = (v, n = 2) => (v == null ? "&mdash;" : v.toFixed(n));
    const tag = d.toLocaleDateString("de-DE", {day:"2-digit",month:"short",year:"numeric"});
    // Bewusst ohne Uhrzeit: Der Zeitstempel ist der *Beginn* der Kerze (09:30 ET),
    // die Hinweiszeile nennt ihren *Schluss* (12:45 ET), und der Browser rechnete
    // beides in seine eigene Zone um. Drei Anker fuer dieselbe Kerze in einem
    // Werkzeug, das gegen einen echten Chart gehalten wird. Datum plus
    // Tageskerzennummer benennt sie eindeutig und braucht keine Zone.
    let h = `<span class="datum">${tag} &middot; ${k.d}. Tageskerze</span>` +
      `O ${z(k.o)}&nbsp; H ${z(k.h)}<br>L ${z(k.l)}&nbsp; <b>C ${z(k.c)}</b><br>` +
      `EMA5 ${z(k.e5)}&nbsp; EMA20 ${z(k.e20)}<br>RSI ${z(k.rsi,1)}&nbsp; MA ${z(k.rma,1)}`;
    if (k.sig) {
      const namen = k.sig.map(s => "&bull; " + (D.kriterien[s] || s)).join("<br>");
      if (k.gate) {
        h += `<br><span class="nein"><b>Verworfen &mdash; ${D.gruende[k.gate] || k.gate}</b>` +
             `<br>${namen}</span>`;
      } else {
        const rolle = k.first ? " (gezaehlt)" : " (Folgetrigger)";
        h += `<br><span class="ja"><b>Kandidat &mdash; Episode ${k.ep + 1}` +
             `${rolle}</b><br>${namen}</span>`;
      }
    }
    tip.innerHTML = h; tip.classList.add("an");
    const r = scroll.getBoundingClientRect();
    let x = cx - r.left + scroll.scrollLeft + 16;
    if (x + tip.offsetWidth > scroll.scrollLeft + scroll.clientWidth)
      x -= tip.offsetWidth + 32;
    let y = cy - r.top + 12;
    if (y + tip.offsetHeight > hoehe) y = hoehe - tip.offsetHeight - 8;
    tip.style.left = x + "px"; tip.style.top = Math.max(4, y) + "px";
  }
  const springe = i => scroll.scrollTo({
    left: Math.max(0, 20 + i * bw() - scroll.clientWidth / 2), behavior: "smooth" });
  document.querySelectorAll("[data-zoom]").forEach(b => b.addEventListener("click", () => {
    const mitte = indexAus(scroll.getBoundingClientRect().left + scroll.clientWidth / 2);
    const neu = zoom + Number(b.dataset.zoom);
    if (neu < 0 || neu > maxZoom()) return;
    zoom = neu; masse(); springe(Math.max(0, Math.min(K.length - 1, mitte))); zeichne();
  }));
  document.getElementById("prev").addEventListener("click", () => {
    const m = indexAus(scroll.getBoundingClientRect().left + scroll.clientWidth / 2);
    const z = [...treffer].reverse().find(i => i < m - 1);
    if (z != null) springe(z);
  });
  document.getElementById("next").addEventListener("click", () => {
    const m = indexAus(scroll.getBoundingClientRect().left + scroll.clientWidth / 2);
    const z = treffer.find(i => i > m + 1);
    if (z != null) springe(z);
  });
  document.getElementById("ende").addEventListener("click",
    () => scroll.scrollTo({ left: breite(), behavior: "smooth" }));
  scroll.addEventListener("scroll", zeichne, { passive: true });
  scroll.addEventListener("keydown", e => {
    const s = scroll.clientWidth * .8;
    if (e.key === "ArrowRight") { scroll.scrollLeft += s; e.preventDefault(); }
    if (e.key === "ArrowLeft") { scroll.scrollLeft -= s; e.preventDefault(); }
  });
  window.addEventListener("resize", () => { masse(); zeichne(); });
  window.matchMedia("(prefers-color-scheme: dark)")
        .addEventListener("change", () => { farben(); zeichne(); });
  document.getElementById("symbol").textContent = D.symbol;
  const a = new Date(K[0].t), b2 = new Date(K[K.length - 1].t);
  const fmt = d => d.toLocaleDateString("de-DE", {day:"2-digit",month:"short",year:"numeric"});
  document.getElementById("spanne").textContent =
    `195-Minuten-Kerzen \\u00b7 ${fmt(a)} bis ${fmt(b2)} \\u00b7 Regel ${D.regelversion}`;
  document.getElementById("kennzahlen").innerHTML = [
    ["Kerzen", K.length], ["geprueft", D.geprueft],
    ["Entscheidungspunkte", D.treffer, "treffer"], ["Episoden", D.episoden],
    ["Verworfen (Tor)", D.verworfen], ["Warm-up", D.warmup],
  ].map(([t, w, c]) => `<div class="kennzahl ${c || ""}"><dt>${t}</dt>` +
       `<dd>${Number(w).toLocaleString("de-DE")}</dd></div>`).join("");
  zoom = Math.min(zoom, maxZoom());
  farben(); masse(); scroll.scrollLeft = breite(); zeichne();
  requestAnimationFrame(zeichne);
})();
</script>
</body>
</html>
"""
