import type { ReactNode } from 'react';

import { Karte } from '@/components/ui/Karte';
import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { ReportDocument } from '@/lib/api';
import { sichereAdresse } from '@/lib/adresse';
import { formatDatum } from '@/lib/format';

import { Restfelder } from '../Restfelder';
import { Vorbehalte } from '../Vorbehalte';
import {
  feldListe,
  feldObjekt,
  feldText,
  feldZahl,
  inhaltObjekt,
  objektliste,
  type JsonObjekt,
} from '../typwaechter';

const SPALTEN: readonly Spalte<JsonObjekt>[] = [
  {
    schluessel: 'period',
    titel: 'Monat',
    kopf: true,
    render: (p) => formatDatum(feldText(p, 'period') ?? ''),
  },
  {
    schluessel: 'strong_buy',
    titel: 'Stark kaufen',
    zahl: true,
    render: (p) => feldZahl(p, 'strong_buy') ?? '–',
  },
  { schluessel: 'buy', titel: 'Kaufen', zahl: true, render: (p) => feldZahl(p, 'buy') ?? '–' },
  { schluessel: 'hold', titel: 'Halten', zahl: true, render: (p) => feldZahl(p, 'hold') ?? '–' },
  { schluessel: 'sell', titel: 'Verkaufen', zahl: true, render: (p) => feldZahl(p, 'sell') ?? '–' },
  {
    schluessel: 'strong_sell',
    titel: 'Stark verkaufen',
    zahl: true,
    render: (p) => feldZahl(p, 'strong_sell') ?? '–',
  },
];

function Votenbalken({ periode }: { periode: JsonObjekt }): ReactNode {
  const teile = [
    ['strong_buy', 'var(--gewinn)'],
    ['buy', 'var(--akzent)'],
    ['hold', 'var(--gedaempft)'],
    ['sell', 'var(--warnung)'],
    ['strong_sell', 'var(--verlust)'],
  ] as const;
  const summe = teile.reduce((s, [k]) => s + (feldZahl(periode, k) ?? 0), 0);
  if (summe === 0) return null;
  return (
    <div className="votenbalken" aria-hidden="true">
      {teile.map(([k, farbe]) => (
        <span
          key={k}
          style={{
            width: `${String(((feldZahl(periode, k) ?? 0) / summe) * 100)}%`,
            background: farbe,
          }}
        />
      ))}
    </div>
  );
}

export function Analysten({ dokument }: { dokument: ReportDocument }): ReactNode {
  const abschnitt = dokument.abschnitte['ANALYSTENMEINUNGEN'];
  const inhalt = inhaltObjekt(abschnitt);
  const empfehlungen = feldObjekt(inhalt, 'empfehlungen');
  const perioden = objektliste(feldListe(empfehlungen, 'periods'));
  const quelle = sichereAdresse(feldText(empfehlungen, 'source_url'));
  return (
    <Karte titel="Analystenmeinungen">
      <Vorbehalte name="ANALYSTENMEINUNGEN" abschnitt={abschnitt} />
      {perioden[0] !== undefined && <Votenbalken periode={perioden[0]} />}
      {perioden.length > 0 && (
        <Tabelle
          spalten={SPALTEN}
          zeilen={perioden}
          schluesselVon={(p) => feldText(p, 'period') ?? JSON.stringify(p)}
          beschriftung="Votenverteilung"
        />
      )}
      {inhalt !== null && 'kursziele' in inhalt && (
        <p className="gedaempft">
          Kursziele: nicht vorhanden (ADR 0043) — die Verteilung der Voten steht hier an ihrer
          Stelle.
        </p>
      )}
      {empfehlungen !== null && (
        <p className="gedaempft">
          Quelle {feldText(empfehlungen, 'source') ?? '–'}
          {quelle !== null && (
            <>
              {' '}
              (
              <a
                href={sichereAdresse(feldText(empfehlungen, 'source_url')) ?? ''}
                target="_blank"
                rel="noopener noreferrer"
              >
                Link
              </a>
              )
            </>
          )}
          {feldText(empfehlungen, 'retrieved_at') !== null && (
            <span> · abgerufen {formatDatum(feldText(empfehlungen, 'retrieved_at') ?? '')}</span>
          )}
        </p>
      )}
      <Restfelder
        objekt={empfehlungen}
        ausser={[
          'periods',
          'source',
          'source_url',
          'retrieved_at',
          'status',
          'evaluated_at',
          'analysis_version',
          'reason',
        ]}
      />
    </Karte>
  );
}
