// Wie Werte angezeigt werden -- Beschriftung und Reihenfolge, sonst nichts.
//
// Keine Fachlogik (Doc 12): Hier wird nichts gerechnet, nichts eingestuft
// und nichts ergaenzt. Was fehlt, bleibt fehlend und bekommt einen Strich.

import type { Recommendation, ReportSummary, RunStatus } from '@/lib/api';

export const LAUFSTATUS_TEXT: Record<RunStatus, string> = {
  SCHEDULED: 'eingeplant',
  RUNNING: 'läuft',
  SCREENING: 'screent',
  COMPLETED: 'abgeschlossen',
  PARTIALLY_COMPLETED: 'teilweise abgeschlossen',
  FAILED: 'gescheitert',
};

export const EMPFEHLUNG_TEXT: Record<Recommendation, string> = {
  STRONG_CANDIDATE: 'starker Kandidat',
  CANDIDATE: 'Kandidat',
  WATCH: 'beobachten',
  AVOID_FOR_NOW: 'vorerst meiden',
  INSUFFICIENT_DATA: 'zu wenig Daten',
};

export function formatZeitpunkt(iso: string): string {
  return new Date(iso).toLocaleString('de-DE', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export function formatScore(wert: number | null): string {
  // Ein Strich und keine Null: Ohne Score gibt es keine Zahl, und eine Null
  // waere die schlechteste Bewertung statt einer fehlenden (ADR 0047).
  return wert === null ? '–' : wert.toFixed(1);
}

export function formatEmpfehlung(stufe: Recommendation | null): string {
  return stufe === null ? '–' : EMPFEHLUNG_TEXT[stufe];
}

export function sortiereNachSwingScore(berichte: readonly ReportSummary[]): ReportSummary[] {
  // Ohne Score ans Ende, nicht als Null nach vorne: Ein Kandidat mit
  // INSUFFICIENT_DATA ist nicht der schlechteste, sondern der unbekannte.
  return [...berichte].sort((links, rechts) => {
    if (links.swing_score === null && rechts.swing_score === null) {
      return links.symbol.localeCompare(rechts.symbol);
    }
    if (links.swing_score === null) return 1;
    if (rechts.swing_score === null) return -1;
    return rechts.swing_score - links.swing_score;
  });
}
