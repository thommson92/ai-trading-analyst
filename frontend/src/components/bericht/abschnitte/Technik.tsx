import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Karte } from '@/components/ui/Karte';
import { Kennzahl, Kennzahlen } from '@/components/ui/Kennzahl';
import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { ReportDocument } from '@/lib/api';
import { beschrifte, formatKurs, formatProzent, formatZeitpunkt } from '@/lib/format';
import { SIGNALBUCHSTABE, SIGNALTEXT } from '@/lib/signale';

import { Restfelder } from '../Restfelder';
import { Vorbehalte } from '../Vorbehalte';
import {
  feldListe,
  feldObjekt,
  feldText,
  feldZahl,
  inhaltListe,
  inhaltObjekt,
  objektliste,
  textliste,
  type JsonObjekt,
} from '../typwaechter';

const TREND_TEXT: Record<string, string | undefined> = {
  UP: 'aufwärts',
  DOWN: 'abwärts',
  SIDEWAYS: 'seitwärts',
};

const ZONEN_SPALTEN: readonly Spalte<JsonObjekt>[] = [
  {
    schluessel: 'kind',
    titel: 'Art',
    kopf: true,
    render: (z) => beschrifte(feldText(z, 'kind') ?? '–'),
  },
  {
    schluessel: 'bereich',
    titel: 'Bereich',
    render: (z) => `${formatKurs(feldZahl(z, 'lower'))} – ${formatKurs(feldZahl(z, 'upper'))}`,
  },
  {
    schluessel: 'strength',
    titel: 'Stärke',
    render: (z) => beschrifte(feldText(z, 'strength') ?? '–'),
  },
  {
    schluessel: 'touch_count',
    titel: 'Berührungen',
    zahl: true,
    render: (z) => feldZahl(z, 'touch_count') ?? '–',
  },
  {
    schluessel: 'distance_pct',
    titel: 'Abstand',
    zahl: true,
    render: (z) => formatProzent(feldZahl(z, 'distance_pct')),
  },
];

const LAGE_FELDER = [
  'close',
  'trend',
  'rsi',
  'ema5',
  'ema20',
  'atr',
  'atr_pct',
  'candle_timestamp',
  'status',
  'evaluated_at',
  'distance_to_ema5_pct',
  'distance_to_ema20_pct',
  'recent_high',
  'recent_low',
  'recent_high_at',
  'recent_low_at',
  'downside_to_support_pct',
  'upside_to_resistance_pct',
  'chance_risk_ratio',
  'zones',
  'analysis_version',
  'parameters',
  'reason',
];
const EINORDNUNG_FELDER = [
  'summary',
  'trend_strength',
  'breakout_quality',
  'momentum_state',
  'swing_entry_plausibility',
  'false_signal_risk',
  'risk_reward_rating',
  'false_signal_risks',
  'confidence',
  'status',
  'evaluated_at',
  'model',
  'prompt_version',
  'interpreted_analysis_version',
  'reason',
];

function Einstufung({
  objekt,
  schluessel,
  label,
}: {
  objekt: JsonObjekt | null;
  schluessel: string;
  label: string;
}): ReactNode {
  const wert = feldText(objekt, schluessel);
  return <Kennzahl label={label} wert={wert === null ? null : beschrifte(wert.toLowerCase())} />;
}

export function Technik({ dokument }: { dokument: ReportDocument }): ReactNode {
  const a = dokument.abschnitte;
  const signale = objektliste(inhaltListe(a['TECHNISCHE_SIGNALE']));
  const lage = inhaltObjekt(a['TECHNISCHE_LAGE']);
  const det = feldObjekt(lage, 'deterministisch');
  const ki = feldObjekt(lage, 'einordnung');
  const zonen = objektliste(inhaltListe(a['ZONEN']));
  const trend = feldText(det, 'trend');
  const risiken = textliste(feldListe(ki, 'false_signal_risks'));
  return (
    <>
      <Karte titel="Ausgelöste Signale">
        <Vorbehalte name="TECHNISCHE_SIGNALE" abschnitt={a['TECHNISCHE_SIGNALE']} />
        {signale.length > 0 && (
          <ul className="signalliste">
            {signale.map((s, stelle) => {
              const typ = feldText(s, 'signal_type') ?? '?';
              return (
                <li key={stelle}>
                  <span className="signalbuchstabe">{SIGNALBUCHSTABE[typ] ?? '?'}</span>{' '}
                  {SIGNALTEXT[typ] ?? beschrifte(typ)}
                  {feldZahl(s, 'candle_index') !== null && (
                    <span className="gedaempft"> · Kerze {feldZahl(s, 'candle_index')}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Karte>
      <Karte titel="Technische Lage (deterministisch)">
        <Vorbehalte name="TECHNISCHE_LAGE" abschnitt={a['TECHNISCHE_LAGE']} />
        {det !== null && (
          <Kennzahlen>
            <Kennzahl
              label="Schluss"
              wert={formatKurs(feldZahl(det, 'close'))}
              hinweis={
                feldText(det, 'candle_timestamp') === null
                  ? undefined
                  : formatZeitpunkt(feldText(det, 'candle_timestamp') ?? '')
              }
            />
            <Kennzahl
              label="Trend"
              wert={trend === null ? null : (TREND_TEXT[trend] ?? beschrifte(trend))}
            />
            <Kennzahl label="RSI" wert={feldZahl(det, 'rsi')?.toFixed(1) ?? null} />
            <Kennzahl label="EMA 5" wert={formatKurs(feldZahl(det, 'ema5'))} />
            <Kennzahl label="EMA 20" wert={formatKurs(feldZahl(det, 'ema20'))} />
            <Kennzahl
              label="ATR"
              wert={formatKurs(feldZahl(det, 'atr'))}
              hinweis={formatProzent(feldZahl(det, 'atr_pct'))}
            />
            <Kennzahl
              label="Abstand EMA 20"
              wert={formatProzent(feldZahl(det, 'distance_to_ema20_pct'))}
            />
            <Kennzahl label="Jüngstes Hoch" wert={formatKurs(feldZahl(det, 'recent_high'))} />
            <Kennzahl label="Jüngstes Tief" wert={formatKurs(feldZahl(det, 'recent_low'))} />
            <Kennzahl
              label="Bis Unterstützung"
              wert={formatProzent(feldZahl(det, 'downside_to_support_pct'))}
            />
            <Kennzahl
              label="Bis Widerstand"
              wert={formatProzent(feldZahl(det, 'upside_to_resistance_pct'))}
            />
            <Kennzahl
              label="Chance/Risiko"
              wert={feldZahl(det, 'chance_risk_ratio')?.toFixed(2) ?? null}
            />
          </Kennzahlen>
        )}
        <Restfelder objekt={det} ausser={LAGE_FELDER} />
      </Karte>
      <Karte titel="KI-Einordnung" kopf={<Badge variante="info">Sprachmodell</Badge>}>
        {ki === null ? (
          <p className="zustand zustand-leer">Keine Einordnung im Bericht.</p>
        ) : (
          <>
            {feldText(ki, 'summary') !== null && (
              <p className="fliesstext">{feldText(ki, 'summary')}</p>
            )}
            <Kennzahlen>
              <Einstufung objekt={ki} schluessel="trend_strength" label="Trendstärke" />
              <Einstufung objekt={ki} schluessel="breakout_quality" label="Ausbruchsqualität" />
              <Einstufung objekt={ki} schluessel="momentum_state" label="Momentum" />
              <Einstufung
                objekt={ki}
                schluessel="swing_entry_plausibility"
                label="Einstieg plausibel"
              />
              <Einstufung objekt={ki} schluessel="false_signal_risk" label="Fehlsignalrisiko" />
              <Einstufung objekt={ki} schluessel="risk_reward_rating" label="Chance/Risiko" />
              <Kennzahl label="Konfidenz" wert={formatProzent(feldZahl(ki, 'confidence'), 0)} />
            </Kennzahlen>
            {risiken.length > 0 && (
              <ul className="liste">
                {risiken.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
            <p className="gedaempft">
              Modell {feldText(ki, 'model') ?? '–'} · Prompt {feldText(ki, 'prompt_version') ?? '–'}
            </p>
            <Restfelder objekt={ki} ausser={EINORDNUNG_FELDER} />
          </>
        )}
      </Karte>
      <Karte titel="Unterstützungen und Widerstände">
        <Vorbehalte name="ZONEN" abschnitt={a['ZONEN']} />
        {zonen.length > 0 && (
          <Tabelle
            spalten={ZONEN_SPALTEN}
            zeilen={zonen}
            schluesselVon={(z) => `${String(feldZahl(z, 'lower'))}-${String(feldZahl(z, 'upper'))}`}
            beschriftung="Zonen"
          />
        )}
      </Karte>
    </>
  );
}
