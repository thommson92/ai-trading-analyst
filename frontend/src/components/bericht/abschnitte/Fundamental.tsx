import type { ReactNode } from 'react';

import { Karte } from '@/components/ui/Karte';
import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { ReportDocument } from '@/lib/api';
import { beschrifte, formatBetrag, formatKurs } from '@/lib/format';

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
  FREE_CASH_FLOW_MARGIN: 'Free-Cashflow-Marge',
  RETURN_ON_EQUITY: 'Eigenkapitalrendite',
  RETURN_ON_ASSETS: 'Gesamtkapitalrendite',
  DEBT_TO_EQUITY: 'Verschuldungsgrad',
  CURRENT_RATIO: 'Liquiditätsgrad',
  SHARE_COUNT_GROWTH: 'Aktienzahl (Veränderung)',
  MARKET_CAPITALIZATION: 'Marktkapitalisierung',
  PRICE_EARNINGS_RATIO: 'KGV',
  PRICE_SALES_RATIO: 'KUV',
  PRICE_FREE_CASH_FLOW_RATIO: 'Kurs/Free Cashflow',
};

// Die Einheiten des Backends (`domain/fundamentals/values.py`, `MetricUnit`):
// FRACTION ist ein Anteil (0,25 = 25 %), RATIO ein dimensionsloses
// Verhaeltnis (KGV 34,2), CURRENCY ein Betrag, SHARES eine Stueckzahl. Eine
// unbekannte Einheit wird nicht geraten: Der Wert steht dann roh mit ihrem
// Namen -- eine Marge von 0,42 als "0" oder ein KGV als "3420 %" waere die
// falsche Zahl mit sicherem Gesicht.
function wertMitEinheit(m: JsonObjekt): string {
  const wert = feldZahl(m, 'value');
  const einheit = feldText(m, 'unit');
  if (wert === null) return '–';
  switch (einheit) {
    case 'FRACTION':
      return `${(wert * 100).toLocaleString('de-DE', { maximumFractionDigits: 1 })} %`;
    case 'RATIO':
      return wert.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    case 'CURRENCY':
      return formatBetrag(wert, feldText(m, 'currency') ?? '');
    case 'SHARES':
      return formatBetrag(wert, 'Stück');
    default:
      return `${String(wert)}${einheit === null ? '' : ` ${einheit}`}`;
  }
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
