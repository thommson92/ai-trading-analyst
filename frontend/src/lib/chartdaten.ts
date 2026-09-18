// Reine Abbildungen fuer den Kerzenchart (ADR 0064): aus dem exportierten
// Chart und den Episoden werden Serien, Marker und Fenster. Nichts wird
// gerechnet, was das Backend nicht schon gerechnet hat -- hier wird nur
// umgeformt, und zwar so, dass es ohne Canvas testbar ist.

import type { BacktestEpisode, Chartkerze, EpisodenHorizont } from '@/lib/api';

/** Sekunden seit der Epoche -- die Zeitachse der Bibliothek. */
export function zeitSekunden(iso: string): number {
  return Math.floor(Date.parse(iso) / 1000);
}

export interface Kerzenpunkt {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface Linienpunkt {
  time: number;
  value?: number;
}

export interface Chartserien {
  kerzen: Kerzenpunkt[];
  ema5: Linienpunkt[];
  ema20: Linienpunkt[];
  rsi: Linienpunkt[];
  rsiDurchschnitt: Linienpunkt[];
  /** Sekunden -> Position in der Kerzenreihe. */
  indexVonZeit: Map<number, number>;
}

function linie(
  kerzen: readonly Chartkerze[],
  wert: (k: Chartkerze) => number | null,
): Linienpunkt[] {
  // Ein fehlender Wert bleibt eine Luecke (Whitespace), keine Null.
  return kerzen.map((k) => {
    const v = wert(k);
    return v === null ? { time: zeitSekunden(k.t) } : { time: zeitSekunden(k.t), value: v };
  });
}

export function kerzenZuSerien(kerzen: readonly Chartkerze[]): Chartserien {
  const indexVonZeit = new Map<number, number>();
  kerzen.forEach((k, stelle) => indexVonZeit.set(zeitSekunden(k.t), stelle));
  return {
    kerzen: kerzen.map((k) => ({
      time: zeitSekunden(k.t),
      open: k.o,
      high: k.h,
      low: k.l,
      close: k.c,
    })),
    ema5: linie(kerzen, (k) => k.e5),
    ema20: linie(kerzen, (k) => k.e20),
    rsi: linie(kerzen, (k) => k.rsi),
    rsiDurchschnitt: linie(kerzen, (k) => k.rma),
    indexVonZeit,
  };
}

export interface Episodenmarker {
  time: number;
  episode: BacktestEpisode;
  /** Das Ergebnis des gewaehlten Horizonts -- null, wenn er nicht erreicht wurde. */
  ergebnis: EpisodenHorizont | null;
}

/** Die Episoden, die auf einer exportierten Kerze liegen -- und die Zahl derer, die es nicht tun. */
export function episodenZuMarkern(
  episoden: readonly BacktestEpisode[],
  serien: Chartserien,
  horizont: number,
): { marker: Episodenmarker[]; ausserhalb: number } {
  const marker: Episodenmarker[] = [];
  let ausserhalb = 0;
  for (const episode of episoden) {
    const time = zeitSekunden(episode.entry_at);
    if (!serien.indexVonZeit.has(time)) {
      ausserhalb += 1;
      continue;
    }
    const ergebnis = episode.horizons.find((h) => h.horizon === horizont) ?? null;
    marker.push({
      time,
      episode,
      ergebnis: ergebnis !== null && ergebnis.return_pct !== null ? ergebnis : null,
    });
  }
  return { marker, ausserhalb };
}

export interface Zeitfenster {
  von: number;
  bis: number;
  horizont: number;
}

/** Die Fenster Einstieg .. Einstieg + H je Horizont, in Kerzenzeit. */
export function horizontfenster(
  serien: Chartserien,
  einstieg: number,
  horizonte: readonly number[],
): Zeitfenster[] {
  const start = serien.indexVonZeit.get(einstieg);
  if (start === undefined) return [];
  const fenster: Zeitfenster[] = [];
  for (const horizont of horizonte) {
    const ende = serien.kerzen[Math.min(start + horizont, serien.kerzen.length - 1)];
    if (ende === undefined) continue;
    fenster.push({ von: einstieg, bis: ende.time, horizont });
  }
  return fenster;
}

/** Der Kurspfad nach dem Einstieg bis zum laengsten Horizont. */
export function pfadNachEinstieg(
  serien: Chartserien,
  einstieg: number,
  laengster: number,
): Linienpunkt[] {
  const start = serien.indexVonZeit.get(einstieg);
  if (start === undefined) return [];
  return serien.kerzen
    .slice(start, start + laengster + 1)
    .map((k) => ({ time: k.time, value: k.close }));
}

/** Die Episode, deren Einstieg auf dieser Zeit liegt. */
export function episodeZurZeit(
  marker: readonly Episodenmarker[],
  time: number,
): BacktestEpisode | null {
  return marker.find((m) => m.time === time)?.episode ?? null;
}
