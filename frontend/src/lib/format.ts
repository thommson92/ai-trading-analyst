// Wie Werte angezeigt werden -- Beschriftung und Reihenfolge, sonst nichts.
//
// Keine Fachlogik (Doc 12): Hier wird nichts gerechnet, nichts eingestuft
// und nichts ergaenzt. Was fehlt, bleibt fehlend und bekommt einen Strich.

import type { Ausgang, Konfidenz, Recommendation, RunStatus } from '@/lib/api';

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

export const ABSCHNITT_TEXT: Record<string, string | undefined> = {
  SYMBOL_UND_UNTERNEHMEN: 'Symbol und Unternehmen',
  ANALYSEZEITPUNKT: 'Analysezeitpunkt',
  TECHNISCHE_SIGNALE: 'Technische Signale',
  EARNINGS_STATUS: 'Berichtstermin',
  SIGNALSTATISTIK: 'Signalstatistik',
  TECHNISCHE_LAGE: 'Technische Lage',
  ZONEN: 'Unterstützungen und Widerstände',
  NACHRICHTEN: 'Nachrichten',
  ANALYSTENMEINUNGEN: 'Analystenmeinungen',
  FUNDAMENTALE_BEWERTUNG: 'Fundamentale Bewertung',
  CHANCEN: 'Chancen',
  RISIKEN: 'Risiken',
  PUT_STRATEGIEN: 'Put-Strategien',
  SWING_SCORE: 'Swing-Score',
  INVESTMENT_SCORE: 'Investment-Score',
  EMPFEHLUNG: 'Empfehlung',
  KONFIDENZ_UND_DATENLUECKEN: 'Konfidenz und Datenlücken',
  QUELLEN: 'Quellen',
};
// Offene Zuordnung mit Rueckfall auf den rohen Namen: Ein neuer Abschnitt
// soll sichtbar sein -- notfalls unschoen --, statt aus der Anzeige zu
// verschwinden, weil hier eine Zeile fehlt.

export function beschrifte(schluessel: string): string {
  const worte = schluessel.replaceAll('_', ' ');
  return worte.charAt(0).toUpperCase() + worte.slice(1);
}

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

export const KONFIDENZ_TEXT: Record<Konfidenz, string> = {
  INSUFFICIENT_DATA: 'zu wenig Daten',
  LOW_SAMPLE: 'kleine Stichprobe',
  NORMAL: 'belastbar',
};

export const AUSGANG_TEXT: Record<Ausgang, string> = {
  EXPIRED_WORTHLESS: 'wertlos verfallen',
  ASSIGNED: 'angedient',
  TAKE_PROFIT: 'Gewinnmitnahme',
  STOPPED_OUT: 'zurückgekauft',
  CLOSED_AT_EXPIRATION: 'am Verfall glattgestellt',
};

export function formatProzent(wert: number | null, stellen = 1): string {
  // Ein Strich und keine Null: Ohne Grundlage gibt es keine Quote, und 0 %
  // waere die schlechteste statt einer fehlenden.
  return wert === null ? '–' : `${(wert * 100).toFixed(stellen)} %`;
}

export function formatGeld(wert: number | null): string {
  if (wert === null) return '–';
  const vorzeichen = wert < 0 ? '−' : '';
  return `${vorzeichen}${Math.abs(wert).toLocaleString('de-DE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} $`;
}

export function formatDatum(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE', { dateStyle: 'medium' });
}
