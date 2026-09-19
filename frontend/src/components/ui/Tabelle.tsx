'use client';

// Eine Tabelle, die sortiert und auf dem Telefon zu Karten wird.
//
// Ein DOM fuer beide Breiten: Unter 40rem schaltet CSS jede Zeile in eine
// Karte, und `data-label` an der Zelle traegt die Spaltenueberschrift. Der
// Kartenmodus ist eine Darstellung, kein zweites Layout im Code.
//
// Sortiert wird hier nach exportierten Werten -- nicht bewertet (Doc 12).

import { useState, type ReactNode } from 'react';

import { sortiert, type Richtung, type Sortierwert } from '@/lib/sortierung';

export interface Spalte<T> {
  schluessel: string;
  titel: string;
  /** Der Inhalt der Zelle. */
  render: (zeile: T) => ReactNode;
  /** Wonach sortiert wird; fehlt er, ist die Spalte nicht sortierbar. */
  sortWert?: (zeile: T) => Sortierwert;
  zahl?: boolean;
  /** Die Zelle traegt die Zeilenueberschrift (`<th scope="row">`). */
  kopf?: boolean;
}

export function Tabelle<T>({
  spalten,
  zeilen,
  schluesselVon,
  sortierung,
  beschriftung,
  zeilenklasse,
}: {
  spalten: readonly Spalte<T>[];
  zeilen: readonly T[];
  schluesselVon: (zeile: T) => string;
  /** Die anfaengliche Sortierung; ohne Angabe bleibt die Reihenfolge der Daten. */
  sortierung?: { schluessel: string; richtung: Richtung };
  beschriftung: string;
  zeilenklasse?: (zeile: T) => string | undefined;
}): ReactNode {
  const [aktiv, setAktiv] = useState(sortierung ?? null);

  const sortSpalte =
    aktiv === null ? undefined : spalten.find((s) => s.schluessel === aktiv.schluessel);
  const sichtbar =
    sortSpalte?.sortWert === undefined || aktiv === null
      ? zeilen
      : sortiert(zeilen, sortSpalte.sortWert, aktiv.richtung);

  function umschalten(spalte: Spalte<T>): void {
    if (spalte.sortWert === undefined) return;
    setAktiv((bisher) =>
      bisher?.schluessel === spalte.schluessel
        ? { schluessel: spalte.schluessel, richtung: bisher.richtung === 'auf' ? 'ab' : 'auf' }
        : { schluessel: spalte.schluessel, richtung: spalte.zahl === true ? 'ab' : 'auf' },
    );
  }

  return (
    <div className="tabelle-kasten">
      <table className="tabelle" aria-label={beschriftung}>
        <thead>
          <tr>
            {spalten.map((spalte) => {
              const richtung =
                aktiv !== null && aktiv.schluessel === spalte.schluessel ? aktiv.richtung : null;
              const sortierbar = spalte.sortWert !== undefined;
              return (
                <th
                  key={spalte.schluessel}
                  scope="col"
                  className={spalte.zahl === true ? 'zahl' : undefined}
                  aria-sort={
                    richtung === null ? undefined : richtung === 'auf' ? 'ascending' : 'descending'
                  }
                >
                  {sortierbar ? (
                    <button
                      type="button"
                      className="sortierknopf"
                      onClick={() => {
                        umschalten(spalte);
                      }}
                    >
                      {spalte.titel}
                      <span className="sortierpfeil" aria-hidden="true">
                        {richtung === null ? '↕' : richtung === 'auf' ? '▲' : '▼'}
                      </span>
                    </button>
                  ) : (
                    spalte.titel
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sichtbar.map((zeile) => (
            <tr key={schluesselVon(zeile)} className={zeilenklasse?.(zeile)}>
              {spalten.map((spalte) =>
                spalte.kopf === true ? (
                  <th key={spalte.schluessel} scope="row" data-label={spalte.titel}>
                    {spalte.render(zeile)}
                  </th>
                ) : (
                  <td
                    key={spalte.schluessel}
                    data-label={spalte.titel}
                    className={spalte.zahl === true ? 'zahl' : undefined}
                  >
                    {spalte.render(zeile)}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
