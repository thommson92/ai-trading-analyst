import type { ReactNode } from 'react';

import { Karte } from '@/components/ui/Karte';
import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { ReportDocument } from '@/lib/api';
import { beschrifte, formatKurs } from '@/lib/format';

import { Restfelder } from '../Restfelder';
import { Vorbehalte } from '../Vorbehalte';
import {
  feldObjekt,
  feldText,
  feldZahl,
  inhaltObjekt,
  istObjekt,
  type JsonObjekt,
} from '../typwaechter';

const KENNZAHL_TEXT: Record<string, string | undefined> = {
  REVENUE: 'Umsatz',
  REVENUE_GROWTH: 'Umsatzwachstum',
  NET_INCOME: 'Nettogewinn',
  NET_INCOME_GROWTH: 'Gewinnwachstum',
  FREE_CASH_FLOW: 'Freier Cashflow',
  GROSS_MARGIN: 'Bruttomarge',
  OPERATING_MARGIN: 'Operative Marge',
  NET_MARGIN: 'Nettomarge',
  DEBT_TO_EQUITY: 'Verschuldungsgrad',
  CURRENT_RATIO: 'Liquiditätsgrad',
  PE_RATIO: 'KGV',
  PRICE_TO_SALES: 'KUV',
  MARKET_CAP: 'Marktkapitalisierung',
};

function waehrung(m: JsonObjekt): string {
  const w = feldText(m, 'currency');
  return w === null ? '' : ` ${w}`;
}

function wertMitEinheit(m: JsonObjekt): string {
  const wert = feldZahl(m, 'value');
  const einheit = feldText(m, 'unit') ?? '';
  if (wert === null) return '–';
  if (einheit === 'RATIO' || einheit === 'PERCENT') return `${(wert * 100).toFixed(1)} %`;
  if (einheit === 'MULTIPLE') return wert.toFixed(2);
  return `${wert.toLocaleString('de-DE', { maximumFractionDigits: 0 })}${waehrung(m)}`;
}

const SPALTEN: readonly Spalte<JsonObjekt>[] = [
  {
    schluessel: 'name',
    titel: 'Kennzahl',
    kopf: true,
    render: (m) =>
      KENNZAHL_TEXT[feldText(m, 'name') ?? ''] ?? beschrifte(feldText(m, 'name') ?? '–'),
  },
  { schluessel: 'value', titel: 'Wert', zahl: true, render: wertMitEinheit },
  {
    schluessel: 'basis',
    titel: 'Basis',
    render: (m) => beschrifte((feldText(m, 'basis') ?? '–').toLowerCase()),
  },
  { schluessel: 'period_end', titel: 'Stichtag', render: (m) => feldText(m, 'period_end') ?? '–' },
];

export function Fundamental({ dokument }: { dokument: ReportDocument }): ReactNode {
  const abschnitt = dokument.abschnitte['FUNDAMENTALE_BEWERTUNG'];
  const inhalt = inhaltObjekt(abschnitt);
  const metriken = feldObjekt(inhalt, 'metrics');
  const zeilen = metriken === null ? [] : Object.values(metriken).filter(istObjekt);
  return (
    <Karte titel="Fundamentale Bewertung">
      <Vorbehalte name="FUNDAMENTALE_BEWERTUNG" abschnitt={abschnitt} />
      {inhalt !== null && (
        <p className="gedaempft">
          {feldText(inhalt, 'company_name') ?? ''}
          {feldZahl(inhalt, 'price_used') !== null && (
            <span> · Kurs der Bewertung {formatKurs(feldZahl(inhalt, 'price_used'))}</span>
          )}
          {feldText(inhalt, 'status') !== null && (
            <span> · {beschrifte((feldText(inhalt, 'status') ?? '').toLowerCase())}</span>
          )}
        </p>
      )}
      {zeilen.length > 0 && (
        <Tabelle
          spalten={SPALTEN}
          zeilen={zeilen}
          schluesselVon={(m) => feldText(m, 'name') ?? JSON.stringify(m)}
          beschriftung="Kennzahlen"
        />
      )}
      <Restfelder
        objekt={inhalt}
        ausser={[
          'metrics',
          'company_name',
          'price_used',
          'status',
          'symbol',
          'evaluated_at',
          'analysis_version',
        ]}
      />
    </Karte>
  );
}
