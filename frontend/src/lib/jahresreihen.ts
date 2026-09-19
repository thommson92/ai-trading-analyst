// Die Jahresreihen der Fundamentalkennzahlen (ADR 0067) in die Form, die ein
// Chart braucht. Reines Umformen exportierter Werte: nichts wird gerechnet,
// nichts eingestuft, nichts ergaenzt (Doc 12).
//
// Gruppiert wird nach der **Einheit**, die das Backend an jede Kennzahl
// schreibt. Das ist keine Wahl der Oberflaeche, sondern die einzige
// Gruppierung, die eine gemeinsame Achse rechtfertigt: Ein Umsatz in Dollar
// und eine Marge als Bruchteil in einem Bild haetten keinen gemeinsamen
// Massstab.

import {
  feldListe,
  feldText,
  feldZahl,
  objektliste,
  type JsonObjekt,
} from '@/components/bericht/typwaechter';

/** Die Einheiten, die das Backend kennt (`domain/fundamentals/values.py`). */
export type Einheit = 'CURRENCY' | 'FRACTION' | 'RATIO' | 'SHARES';

export const EINHEITEN: readonly Einheit[] = ['CURRENCY', 'FRACTION', 'RATIO', 'SHARES'];

export interface Jahrespunkt {
  /** Das Geschaeftsjahr als Zahl -- die Achse des Charts. */
  jahr: number;
  /** Je Kennzahlname der Wert dieses Jahres; fehlende Jahre fehlen. */
  werte: Record<string, number | undefined>;
}

export interface Kennzahlenreihe {
  einheit: Einheit;
  /** Die Kennzahlen dieser Einheit, in der Reihenfolge des Dokuments. */
  namen: string[];
  punkte: Jahrespunkt[];
  /** Die Waehrung, wenn alle Betraege dieselbe nennen -- sonst null. */
  waehrung: string | null;
}

interface Jahreszeile {
  jahr: number;
  metriken: JsonObjekt[];
}

function jahreszeilen(inhalt: JsonObjekt | null): Jahreszeile[] {
  const zeilen: Jahreszeile[] = [];
  for (const eintrag of objektliste(feldListe(inhalt, 'history'))) {
    const ende = feldText(eintrag, 'period_end');
    const jahr = ende === null ? NaN : Number(ende.slice(0, 4));
    if (!Number.isFinite(jahr)) continue;
    zeilen.push({ jahr, metriken: objektliste(feldListe(eintrag, 'metrics')) });
  }
  return zeilen.sort((a, b) => a.jahr - b.jahr);
}

/**
 * Eine Reihe je Einheit, jede mit ihren Kennzahlen und Jahren. Einheiten
 * ohne eine einzige Zahl entstehen nicht.
 */
export function reihenAusDokument(inhalt: JsonObjekt | null): Kennzahlenreihe[] {
  const zeilen = jahreszeilen(inhalt);
  if (zeilen.length === 0) return [];
  const reihen: Kennzahlenreihe[] = [];
  for (const einheit of EINHEITEN) {
    const namen: string[] = [];
    const waehrungen = new Set<string>();
    const punkte: Jahrespunkt[] = [];
    for (const zeile of zeilen) {
      const werte: Record<string, number | undefined> = {};
      for (const metrik of zeile.metriken) {
        if (feldText(metrik, 'unit') !== einheit) continue;
        const name = feldText(metrik, 'name');
        const wert = feldZahl(metrik, 'value');
        if (name === null || wert === null) continue;
        if (!namen.includes(name)) namen.push(name);
        werte[name] = wert;
        const waehrung = feldText(metrik, 'currency');
        if (waehrung !== null) waehrungen.add(waehrung);
      }
      punkte.push({ jahr: zeile.jahr, werte });
    }
    if (namen.length === 0) continue;
    // Nur wenn alle Betraege dieselbe Waehrung nennen, darf sie in der
    // Ueberschrift stehen -- sonst stuende eine Zahl unter einem Zeichen,
    // das nicht zu ihr gehoert.
    const [einzige] = [...waehrungen];
    reihen.push({
      einheit,
      namen,
      punkte,
      waehrung: waehrungen.size === 1 && einzige !== undefined ? einzige : null,
    });
  }
  return reihen;
}

/** Die Geschaeftsjahre, die im Kopf des Abschnitts stehen (ohne Historie). */
export function berichtsjahre(inhalt: JsonObjekt | null): number[] {
  return feldListe(inhalt, 'fiscal_years').filter((w): w is number => typeof w === 'number');
}

/** Der Abschnittsinhalt, wenn er eine Historie traegt -- sonst null. */
export function hatHistorie(inhalt: JsonObjekt | null): boolean {
  return jahreszeilen(inhalt).length > 0;
}
