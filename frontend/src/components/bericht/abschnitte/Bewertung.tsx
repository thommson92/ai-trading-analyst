import type { ReactNode } from 'react';

import { Karte } from '@/components/ui/Karte';
import { Kennzahl, Kennzahlen } from '@/components/ui/Kennzahl';
import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { ReportDocument } from '@/lib/api';
import { ABSCHNITT_TEXT, beschrifte, formatProzent, formatScore } from '@/lib/format';

import { Restfelder } from '../Restfelder';
import { Vorbehalte } from '../Vorbehalte';
import {
  feldListe,
  feldText,
  feldZahl,
  inhaltObjekt,
  objektliste,
  textliste,
  type JsonObjekt,
} from '../typwaechter';

const KOMPONENTE_TEXT: Record<string, string | undefined> = {
  TECHNICAL_SIGNALS: 'Technische Signale',
  SIGNAL_STATISTICS: 'Signalstatistik',
  CHART_SETUP: 'Chartbild',
  CHANCE_RISK: 'Chance/Risiko',
  NEWS_AND_EVENTS: 'Nachrichten und Ereignisse',
  OPTIONS_ATTRACTIVENESS: 'Optionsattraktivität',
  REVENUE_GROWTH: 'Umsatzwachstum',
  PROFITABILITY: 'Profitabilität',
  BALANCE_SHEET: 'Bilanz',
  VALUATION: 'Bewertung',
  CASH_FLOW: 'Cashflow',
};

const KOMPONENTEN: readonly Spalte<JsonObjekt>[] = [
  {
    schluessel: 'name',
    titel: 'Komponente',
    kopf: true,
    render: (k) =>
      KOMPONENTE_TEXT[feldText(k, 'name') ?? ''] ?? beschrifte(feldText(k, 'name') ?? '–'),
  },
  {
    schluessel: 'value',
    titel: 'Teilwert',
    zahl: true,
    render: (k) => formatScore(feldZahl(k, 'value')),
  },
  {
    schluessel: 'weight',
    titel: 'Gewicht',
    zahl: true,
    render: (k) => formatProzent(feldZahl(k, 'weight'), 0),
  },
  {
    schluessel: 'effective_weight',
    titel: 'Wirksam',
    zahl: true,
    render: (k) => formatProzent(feldZahl(k, 'effective_weight'), 0),
  },
  { schluessel: 'reason', titel: 'Hinweis', render: (k) => feldText(k, 'reason') ?? '' },
];

function Score({
  name,
  dokument,
}: {
  name: 'SWING_SCORE' | 'INVESTMENT_SCORE';
  dokument: ReportDocument;
}): ReactNode {
  const abschnitt = dokument.abschnitte[name];
  const inhalt = inhaltObjekt(abschnitt);
  const komponenten = objektliste(feldListe(inhalt, 'components'));
  return (
    <Karte titel={ABSCHNITT_TEXT[name] ?? name}>
      <Vorbehalte name={name} abschnitt={abschnitt} />
      {inhalt !== null && (
        <>
          <Kennzahlen>
            <Kennzahl label="Wert" wert={formatScore(feldZahl(inhalt, 'value'))} betont />
            <Kennzahl
              label="Status"
              wert={beschrifte((feldText(inhalt, 'status') ?? '–').toLowerCase())}
            />
            <Kennzahl label="Abdeckung" wert={formatProzent(feldZahl(inhalt, 'coverage'), 0)} />
            <Kennzahl
              label="Konfidenz"
              wert={beschrifte((feldText(inhalt, 'confidence') ?? '–').toLowerCase())}
            />
          </Kennzahlen>
          {komponenten.length > 0 && (
            <Tabelle
              spalten={KOMPONENTEN}
              zeilen={komponenten}
              schluesselVon={(k) => feldText(k, 'name') ?? JSON.stringify(k)}
              beschriftung="Komponenten"
            />
          )}
          {(['positive_factors', 'negative_factors', 'limiting_risks'] as const).map(
            (schluessel) => {
              const punkte = textliste(feldListe(inhalt, schluessel));
              return punkte.length === 0 ? null : (
                <div key={schluessel}>
                  <p className="gedaempft">{beschrifte(schluessel)}</p>
                  <ul className="liste">
                    {punkte.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                </div>
              );
            },
          )}
          <Restfelder
            objekt={inhalt}
            ausser={[
              'value',
              'status',
              'coverage',
              'confidence',
              'components',
              'positive_factors',
              'negative_factors',
              'limiting_risks',
              'kind',
              'version',
            ]}
          />
        </>
      )}
    </Karte>
  );
}

export function Bewertung({ dokument }: { dokument: ReportDocument }): ReactNode {
  const empfehlung = inhaltObjekt(dokument.abschnitte['EMPFEHLUNG']);
  const konfidenz = inhaltObjekt(dokument.abschnitte['KONFIDENZ_UND_DATENLUECKEN']);
  const luecken = objektliste(feldListe(konfidenz, 'luecken'));
  return (
    <>
      <Karte titel="Empfehlung">
        <Vorbehalte name="EMPFEHLUNG" abschnitt={dokument.abschnitte['EMPFEHLUNG']} />
        {empfehlung !== null && (
          <>
            <p>
              <strong>{beschrifte((feldText(empfehlung, 'stufe') ?? '–').toLowerCase())}</strong>
              {feldText(empfehlung, 'zusammenfassung') !== null && (
                <span> — {feldText(empfehlung, 'zusammenfassung')}</span>
              )}
            </p>
            {textliste(feldListe(empfehlung, 'begruendung')).length > 0 && (
              <ul className="liste">
                {textliste(feldListe(empfehlung, 'begruendung')).map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            )}
            {textliste(feldListe(empfehlung, 'deckelungen')).length > 0 && (
              <p className="gedaempft">
                Deckelungen: {textliste(feldListe(empfehlung, 'deckelungen')).join(', ')}
              </p>
            )}
            <Restfelder
              objekt={empfehlung}
              ausser={['stufe', 'begruendung', 'deckelungen', 'version', 'zusammenfassung']}
            />
          </>
        )}
      </Karte>
      <div className="zweispaltig">
        <Score name="SWING_SCORE" dokument={dokument} />
        <Score name="INVESTMENT_SCORE" dokument={dokument} />
      </div>
      <Karte titel="Konfidenz und Datenlücken">
        {luecken.length === 0 ? (
          <p className="zustand zustand-leer">Keine Lücken vermerkt.</p>
        ) : (
          <ul className="liste">
            {luecken.map((l, stelle) => (
              <li key={stelle}>
                <strong>
                  {ABSCHNITT_TEXT[feldText(l, 'abschnitt') ?? ''] ?? feldText(l, 'abschnitt')}
                </strong>{' '}
                ({beschrifte((feldText(l, 'art') ?? '').toLowerCase())}): {feldText(l, 'grund')}
              </li>
            ))}
          </ul>
        )}
        <Restfelder objekt={konfidenz} ausser={['luecken', 'fehlende_abschnitte', 'konfidenzen']} />
      </Karte>
    </>
  );
}
