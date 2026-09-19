// Wie Werte angezeigt werden -- Beschriftung und Reihenfolge, sonst nichts.
//
// Keine Fachlogik (Doc 12): Hier wird nichts gerechnet, nichts eingestuft
// und nichts ergaenzt. Was fehlt, bleibt fehlend und bekommt einen Strich.

import type { Ausgang, EarningsStatus, Konfidenz, Recommendation, RunStatus } from '@/lib/api';

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
  // Ein reines Datum (`2026-03-06`) liest JavaScript als UTC-Mitternacht und
  // verschiebt es damit in westlichen Zeitzonen auf den Vortag. Hier steht
  // aber ein Handelstag, kein Zeitpunkt -- er hat keine Zeitzone, und ein
  // Tag Versatz wäre schlicht das falsche Datum.
  const nurDatum = /^\d{4}-\d{2}-\d{2}$/.exec(iso);
  const zeitpunkt =
    nurDatum === null
      ? new Date(iso)
      : new Date(
          Number(iso.slice(0, 4)),
          Number(iso.slice(5, 7)) - 1,
          Number(iso.slice(8, 10)),
        );
  // Ein Wert, der kein Datum ist, bleibt sichtbar, wie er ist -- besser
  // als "Invalid Date", und nichts wird still zu einem Strich.
  if (Number.isNaN(zeitpunkt.getTime())) return iso === '' ? '–' : iso;
  return zeitpunkt.toLocaleDateString('de-DE', { dateStyle: 'medium' });
}

/**
 * Die Reihenfolge der Stufen, wie das Backend sie deklariert
 * (`domain/scoring/values.py`, `Recommendation`) -- zum Sortieren einer
 * Spalte. Alphabetisch stuende "stark" zwischen "zu wenig Daten" und
 * "beobachten". Das ist Anzeigereihenfolge, keine Bewertung: Die Stufe
 * selbst vergibt das Backend.
 */
export const EMPFEHLUNG_REIHENFOLGE: readonly Recommendation[] = [
  'STRONG_CANDIDATE',
  'CANDIDATE',
  'WATCH',
  'AVOID_FOR_NOW',
  'INSUFFICIENT_DATA',
];

export function empfehlungsrang(stufe: Recommendation | null | undefined): number | null {
  if (stufe === null || stufe === undefined) return null;
  const rang = EMPFEHLUNG_REIHENFOLGE.indexOf(stufe);
  return rang < 0 ? null : rang;
}

export const EARNINGS_TEXT: Record<EarningsStatus, string> = {
  EARNINGS_CLEAR: 'Berichtstermin frei',
  EARNINGS_EXCLUDED: 'Berichtstermin im Fenster',
  // "Unbekannt" ist kein belegter Nichttermin (ADR 0020) -- die Karte sagt
  // das ausdruecklich, statt es wie "frei" aussehen zu lassen.
  UNKNOWN: 'Termin unbekannt',
};

export const FEHLSIGNALRISIKO_TEXT: Record<string, string | undefined> = {
  LOW: 'niedrig',
  MEDIUM: 'mittel',
  HIGH: 'hoch',
};

export const LIQUIDITAET_TEXT: Record<string, string | undefined> = {
  GOOD: 'liquide',
  ACCEPTABLE: 'ausreichend liquide',
  POOR: 'wenig liquide',
};

/** Ein Kurs, wie er auf einer Karte steht: zwei Stellen, Dollar, Strich ohne Wert. */
export function formatKurs(wert: number | null): string {
  return wert === null ? '–' : `${wert.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
}

/**
 * Ein grosser Betrag lesbar: 62.363.000.000 wird zu "62,36 Mrd.", Millionen
 * zu "Mio.", darunter bleibt die volle Zahl. Nur Darstellung -- der Wert
 * selbst steht unveraendert im Bericht.
 */
export function formatBetrag(wert: number | null, einheit = ''): string {
  if (wert === null) return '–';
  const betrag = Math.abs(wert);
  const [teiler, stufe] = betrag >= 1e9 ? [1e9, ' Mrd.'] : betrag >= 1e6 ? [1e6, ' Mio.'] : [1, ''];
  const zahl = (wert / teiler).toLocaleString('de-DE', {
    maximumFractionDigits: teiler === 1 ? 0 : 2,
  });
  return `${zahl}${stufe}${einheit === '' ? '' : ` ${einheit}`}`;
}

/** Ein Zeitpunkt nur als Datum -- fuer Listen, in denen die Uhrzeit nichts sagt. */
export function formatTag(iso: string | null): string {
  return iso === null ? '–' : formatDatum(iso);
}
