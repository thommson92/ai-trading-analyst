'use client';

// Der Kerzenchart (ADR 0064): Kerzen mit EMA 5 und EMA 20, darunter der RSI,
// die Episoden-Einstiege als Marker, nach Klick das Horizontfenster und der
// Kurspfad. Die Bibliothek zeichnet auf Canvas und kennt keine CSS-Variablen;
// die Farben kommen aus den Tokens, gelesen beim Aufbau und bei jedem
// Themenwechsel.
//
// Attribution: Die Bibliothek zeichnet ihr eigenes Logo mit Link
// (`attributionLogo`), so wie ihre Lizenz es verlangt. Kein `href` aus
// Daten -- der Sicherheitstest bleibt unberuehrt.

import {
  CandlestickSeries,
  CrosshairMode,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import { useEffect, useRef, type ReactNode } from 'react';

import {
  episodenZuMarkern,
  horizontfenster,
  kerzenZuSerien,
  pfadNachEinstieg,
  zeitSekunden,
  type Chartserien,
} from '@/lib/chartdaten';
import type { BacktestEpisode, Chartdaten } from '@/lib/api';

import { Horizontfenster } from './Horizontfenster';

const HORIZONTE = [5, 10, 20] as const;

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

interface Aufbau {
  chart: IChartApi;
  kerzen: ISeriesApi<'Candlestick'>;
  ema5: ISeriesApi<'Line'>;
  ema20: ISeriesApi<'Line'>;
  rsi: ISeriesApi<'Line'>;
  rsiDurchschnitt: ISeriesApi<'Line'>;
  pfad: ISeriesApi<'Line'>;
  marker: ISeriesMarkersPluginApi<Time>;
  fenster: Horizontfenster;
}

function farbenAnwenden(a: Aufbau): void {
  a.chart.applyOptions({
    layout: {
      background: { color: token('--flaeche') },
      textColor: token('--gedaempft'),
      fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      attributionLogo: true,
    },
    grid: { vertLines: { color: token('--linie') }, horzLines: { color: token('--linie') } },
    rightPriceScale: { borderColor: token('--linie') },
    timeScale: { borderColor: token('--linie') },
  });
  a.kerzen.applyOptions({
    upColor: token('--kerze-auf'),
    downColor: token('--kerze-ab'),
    wickUpColor: token('--kerze-auf'),
    wickDownColor: token('--kerze-ab'),
    borderVisible: false,
  });
  a.ema5.applyOptions({ color: token('--ema5') });
  a.ema20.applyOptions({ color: token('--ema20') });
  a.rsi.applyOptions({ color: token('--rsi') });
  a.rsiDurchschnitt.applyOptions({ color: token('--gedaempft') });
  a.pfad.applyOptions({ color: token('--akzent') });
}

export function Kerzenchart({
  daten,
  episoden,
  gewaehlt,
  horizont,
  laufzeitpunkt,
  onWahl,
  onAusserhalb,
}: {
  daten: Chartdaten;
  episoden: readonly BacktestEpisode[];
  gewaehlt: BacktestEpisode | null;
  horizont: number;
  /** Die Entscheidungskerze eines Laufs, aus dem der Leser kommt. */
  laufzeitpunkt: string | null;
  onWahl: (episode: BacktestEpisode | null) => void;
  onAusserhalb: (anzahl: number) => void;
}): ReactNode {
  const behaelter = useRef<HTMLDivElement>(null);
  const aufbau = useRef<Aufbau | null>(null);
  const serien = useRef<Chartserien | null>(null);
  // Der Klick-Handler haengt am Chart, die Marker aendern sich mit dem
  // Horizont: Der Handler liest sie ueber diese Referenz, nicht ueber eine
  // eingefrorene Closure.
  const markerZeiten = useRef<Map<number, BacktestEpisode>>(new Map());
  const wahl = useRef(onWahl);
  wahl.current = onWahl;

  // Aufbau einmal je Kursreihe.
  useEffect(() => {
    const element = behaelter.current;
    if (element === null) return;
    const chart = createChart(element, {
      autoSize: true,
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { timeVisible: true, secondsVisible: false, rightOffset: 4 },
      handleScroll: true,
      handleScale: true,
      localization: { locale: 'de-DE' },
    });
    const kerzen = chart.addSeries(CandlestickSeries, {
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    const ema5 = chart.addSeries(LineSeries, {
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      title: 'EMA 5',
    });
    const ema20 = chart.addSeries(LineSeries, {
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      title: 'EMA 20',
    });
    const pfad = chart.addSeries(LineSeries, {
      lineWidth: 3,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const rsi = chart.addSeries(
      LineSeries,
      { lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'RSI' },
      1,
    );
    const rsiDurchschnitt = chart.addSeries(
      LineSeries,
      {
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      1,
    );
    for (const stufe of [30, 50, 70]) {
      rsi.createPriceLine({
        price: stufe,
        color: token('--linie'),
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: false,
        title: '',
      });
    }
    chart.panes()[1]?.setHeight(110);
    const fenster = new Horizontfenster();
    kerzen.attachPrimitive(fenster);
    const marker = createSeriesMarkers(kerzen, []);

    const gebaut: Aufbau = {
      chart,
      kerzen,
      ema5,
      ema20,
      rsi,
      rsiDurchschnitt,
      pfad,
      marker,
      fenster,
    };
    aufbau.current = gebaut;
    const abgebildet = kerzenZuSerien(daten.kerzen);
    serien.current = abgebildet;
    kerzen.setData(abgebildet.kerzen.map((k) => ({ ...k, time: k.time as UTCTimestamp })));
    ema5.setData(abgebildet.ema5.map((p) => ({ ...p, time: p.time as UTCTimestamp })));
    ema20.setData(abgebildet.ema20.map((p) => ({ ...p, time: p.time as UTCTimestamp })));
    rsi.setData(abgebildet.rsi.map((p) => ({ ...p, time: p.time as UTCTimestamp })));
    rsiDurchschnitt.setData(
      abgebildet.rsiDurchschnitt.map((p) => ({ ...p, time: p.time as UTCTimestamp })),
    );
    farbenAnwenden(gebaut);
    // Die letzten ~120 Kerzen (ein Vierteljahr) sind der Einstieg; die ganze
    // Historie bleibt per Zoom erreichbar.
    chart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, abgebildet.kerzen.length - 120),
      to: abgebildet.kerzen.length + 3,
    });

    function beiKlick(param: MouseEventParams): void {
      const zeit = typeof param.time === 'number' ? param.time : null;
      wahl.current(zeit === null ? null : (markerZeiten.current.get(zeit) ?? null));
    }
    chart.subscribeClick(beiKlick);

    const beobachter = new MutationObserver(() => {
      farbenAnwenden(gebaut);
    });
    beobachter.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-thema'],
    });

    return () => {
      beobachter.disconnect();
      chart.unsubscribeClick(beiKlick);
      chart.remove();
      aufbau.current = null;
      serien.current = null;
    };
  }, [daten]);

  // Marker: Episoden plus Laufzeitpunkt, gefaerbt nach dem gewaehlten Horizont.
  useEffect(() => {
    const a = aufbau.current;
    const s = serien.current;
    if (a === null || s === null) return;
    const { marker, ausserhalb } = episodenZuMarkern(episoden, s, horizont);
    onAusserhalb(ausserhalb);
    markerZeiten.current = new Map(marker.map((m) => [m.time, m.episode]));
    const gewinn = token('--gewinn');
    const verlust = token('--verlust');
    const offen = token('--gedaempft');
    const liste: SeriesMarker<Time>[] = marker.map((m) => ({
      time: m.time as UTCTimestamp,
      position: 'belowBar',
      shape: 'arrowUp',
      color: m.ergebnis === null ? offen : (m.ergebnis.return_pct ?? 0) > 0 ? gewinn : verlust,
      text: m.episode.letters,
      size: gewaehlt !== null && zeitSekunden(gewaehlt.entry_at) === m.time ? 2 : 1,
    }));
    if (laufzeitpunkt !== null) {
      const zeit = zeitSekunden(laufzeitpunkt);
      if (s.indexVonZeit.has(zeit)) {
        liste.push({
          time: zeit as UTCTimestamp,
          position: 'aboveBar',
          shape: 'circle',
          color: token('--akzent'),
          text: 'Lauf',
        });
      }
    }
    liste.sort((x, y) => (x.time as number) - (y.time as number));
    a.marker.setMarkers(liste);
  }, [episoden, horizont, gewaehlt, laufzeitpunkt, onAusserhalb]);

  // Fenster und Pfad der gewaehlten Episode.
  useEffect(() => {
    const a = aufbau.current;
    const s = serien.current;
    if (a === null || s === null) return;
    if (gewaehlt === null) {
      a.fenster.setze([], { farbe: token('--akzent'), betont: null });
      a.pfad.setData([]);
      return;
    }
    const einstieg = zeitSekunden(gewaehlt.entry_at);
    const horizonte = gewaehlt.horizons.map((h) => h.horizon);
    a.fenster.setze(horizontfenster(s, einstieg, horizonte), {
      farbe: token('--akzent'),
      betont: horizont,
    });
    const laengster = Math.max(...horizonte, ...HORIZONTE);
    a.pfad.setData(
      pfadNachEinstieg(s, einstieg, laengster).map((p) => ({ ...p, time: p.time as UTCTimestamp })),
    );
    const stelle = s.indexVonZeit.get(einstieg);
    if (stelle !== undefined) {
      a.chart
        .timeScale()
        .setVisibleLogicalRange({ from: stelle - 40, to: stelle + laengster + 20 });
    }
  }, [gewaehlt, horizont]);

  return (
    <div
      className="kerzenchart"
      ref={behaelter}
      role="img"
      aria-label={`Kursverlauf ${daten.symbol}`}
    />
  );
}
