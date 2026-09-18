// Vergleichen, nicht bewerten: Diese Funktionen ordnen exportierte Werte.
// Was "gut" heisst, entscheidet nicht die Oberflaeche (Doc 12).

export type Sortierwert = string | number | boolean | null | undefined;

export type Richtung = 'auf' | 'ab';

/**
 * Vergleicht zwei Werte; fehlende Werte stehen **immer zuletzt**, egal in
 * welche Richtung sortiert wird -- ein Strich ist keine kleinste Zahl.
 */
export function vergleiche(a: Sortierwert, b: Sortierwert, richtung: Richtung = 'auf'): number {
  const aFehlt = a === null || a === undefined;
  const bFehlt = b === null || b === undefined;
  if (aFehlt && bFehlt) return 0;
  if (aFehlt) return 1;
  if (bFehlt) return -1;
  let ergebnis: number;
  if (typeof a === 'number' && typeof b === 'number') {
    ergebnis = a - b;
  } else if (typeof a === 'boolean' && typeof b === 'boolean') {
    ergebnis = Number(a) - Number(b);
  } else {
    ergebnis = String(a).localeCompare(String(b), 'de');
  }
  return richtung === 'auf' ? ergebnis : -ergebnis;
}

/** Stabil sortiert nach einem Schluessel; das Original bleibt unberuehrt. */
export function sortiert<T>(
  zeilen: readonly T[],
  wertVon: (zeile: T) => Sortierwert,
  richtung: Richtung = 'auf',
): T[] {
  return zeilen
    .map((zeile, stelle) => ({ zeile, stelle }))
    .sort((x, y) => vergleiche(wertVon(x.zeile), wertVon(y.zeile), richtung) || x.stelle - y.stelle)
    .map((eintrag) => eintrag.zeile);
}
