// Filtern, gruppieren, zaehlen -- ueber exportierte Episoden (ADR 0061).
// Nichts hier bewertet: Eine Trefferquote je Quartal ist eine Zaehlung, kein
// Urteil, und die Schwellen der Konfidenz kommen weiterhin aus dem Backend.

import type { BacktestEpisode, EpisodenHorizont } from '@/lib/api';

export interface Episodenfilter {
  /** Signalbuchstaben, z. B. 'ABD'; leer = alle. */
  kombination: string;
  von: string;
  bis: string;
}

export function ergebnisFuer(episode: BacktestEpisode, horizont: number): EpisodenHorizont | null {
  return episode.horizons.find((h) => h.horizon === horizont) ?? null;
}

export function gefiltert(
  episoden: readonly BacktestEpisode[],
  filter: Episodenfilter,
): BacktestEpisode[] {
  return episoden.filter(
    (e) =>
      (filter.kombination === '' || e.letters === filter.kombination) &&
      (filter.von === '' || e.entry_at.slice(0, 10) >= filter.von) &&
      (filter.bis === '' || e.entry_at.slice(0, 10) <= filter.bis),
  );
}

export function kombinationen(episoden: readonly BacktestEpisode[]): string[] {
  return [...new Set(episoden.map((e) => e.letters))].sort();
}

export interface Quartal {
  quartal: string;
  anzahl: number;
  treffer: number;
  /** null, wenn keine Episode den Horizont erreicht hat -- kein Ersatzwert. */
  quote: number | null;
}

export function quartalVon(iso: string): string {
  const jahr = iso.slice(0, 4);
  const monat = Number(iso.slice(5, 7));
  return `${jahr} Q${String(Math.floor((monat - 1) / 3) + 1)}`;
}

/** Je Quartal: wie viele Episoden den Horizont erreichten und wie viele davon ueber null lagen. */
export function quartale(episoden: readonly BacktestEpisode[], horizont: number): Quartal[] {
  const gruppen = new Map<string, { anzahl: number; treffer: number }>();
  for (const e of episoden) {
    const ergebnis = ergebnisFuer(e, horizont);
    if (ergebnis?.return_pct === null || ergebnis === null) continue;
    const q = quartalVon(e.entry_at);
    const g = gruppen.get(q) ?? { anzahl: 0, treffer: 0 };
    g.anzahl += 1;
    if (ergebnis.return_pct > 0) g.treffer += 1;
    gruppen.set(q, g);
  }
  return [...gruppen.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([quartal, g]) => ({
      quartal,
      anzahl: g.anzahl,
      treffer: g.treffer,
      quote: g.anzahl === 0 ? null : g.treffer / g.anzahl,
    }));
}

export interface Extreme {
  beste: BacktestEpisode | null;
  schlechteste: BacktestEpisode | null;
}

export function extreme(episoden: readonly BacktestEpisode[], horizont: number): Extreme {
  let beste: BacktestEpisode | null = null;
  let schlechteste: BacktestEpisode | null = null;
  let max = -Infinity;
  let min = Infinity;
  for (const e of episoden) {
    const r = ergebnisFuer(e, horizont)?.return_pct ?? null;
    if (r === null) continue;
    if (r > max) {
      max = r;
      beste = e;
    }
    if (r < min) {
      min = r;
      schlechteste = e;
    }
  }
  return { beste, schlechteste };
}

/** Die Renditen aller Episoden, die den Horizont erreicht haben. */
export function renditen(episoden: readonly BacktestEpisode[], horizont: number): number[] {
  return episoden
    .map((e) => ergebnisFuer(e, horizont)?.return_pct ?? null)
    .filter((r): r is number => r !== null);
}
