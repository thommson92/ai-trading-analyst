import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Karte } from '@/components/ui/Karte';
import { Kennzahl, Kennzahlen } from '@/components/ui/Kennzahl';
import type { ReportDocument } from '@/lib/api';
import { LIQUIDITAET_TEXT, beschrifte, formatKurs, formatProzent, formatTag } from '@/lib/format';

import { Restfelder } from '../Restfelder';
import { Vorbehalte } from '../Vorbehalte';
import {
  feldListe,
  feldObjekt,
  feldText,
  feldWahrheit,
  feldZahl,
  inhaltObjekt,
  objektliste,
  textliste,
  type JsonObjekt,
} from '../typwaechter';

const PUT_FELDER = [
  'strike',
  'expiration',
  'days_to_expiration',
  'premium',
  'bid',
  'ask',
  'mid',
  'delta',
  'implied_volatility',
  'open_interest',
  'volume',
  'break_even',
  'capital_at_risk',
  'simple_return',
  'annualized_return',
  'distance_to_price_pct',
  'distance_to_support_pct',
  'liquidity',
  'liquidity_warnings',
  'earnings_within_term',
];

function Vorschlag({ put, rang }: { put: JsonObjekt; rang: number }): ReactNode {
  const warnungen = textliste(feldListe(put, 'liquidity_warnings'));
  const liquiditaet = feldText(put, 'liquidity');
  return (
    <Karte
      className="putkarte"
      titel={`${String(rang)}. Strike ${formatKurs(feldZahl(put, 'strike'))} · Verfall ${formatTag(feldText(put, 'expiration'))}`}
      kopf={
        <>
          {liquiditaet !== null && <Badge>{LIQUIDITAET_TEXT[liquiditaet] ?? liquiditaet}</Badge>}
          {feldWahrheit(put, 'earnings_within_term') === true && (
            <Badge variante="warnung">Berichtstermin in der Laufzeit</Badge>
          )}
        </>
      }
    >
      <Kennzahlen>
        <Kennzahl
          label="Prämie je Aktie"
          wert={formatKurs(feldZahl(put, 'premium'))}
          hinweis={`Geld ${formatKurs(feldZahl(put, 'bid'))} · Brief ${formatKurs(feldZahl(put, 'ask'))}`}
          betont
        />
        <Kennzahl
          label="Rendite p. a."
          wert={formatProzent(feldZahl(put, 'annualized_return'))}
          hinweis={`einfach ${formatProzent(feldZahl(put, 'simple_return'))}`}
        />
        <Kennzahl
          label="Laufzeit"
          wert={`${String(feldZahl(put, 'days_to_expiration') ?? '–')} Tage`}
        />
        <Kennzahl
          label="Abstand zum Kurs"
          wert={formatProzent(feldZahl(put, 'distance_to_price_pct'))}
          hinweis={
            feldZahl(put, 'distance_to_support_pct') === null
              ? 'ohne Zonenbezug'
              : `zur Unterstützung ${formatProzent(feldZahl(put, 'distance_to_support_pct'))}`
          }
        />
        <Kennzahl label="Break-even" wert={formatKurs(feldZahl(put, 'break_even'))} />
        <Kennzahl label="Gebundenes Kapital" wert={formatKurs(feldZahl(put, 'capital_at_risk'))} />
        <Kennzahl label="Delta" wert={feldZahl(put, 'delta')?.toFixed(2) ?? null} />
        <Kennzahl
          label="Implizite Vola"
          wert={formatProzent(feldZahl(put, 'implied_volatility'))}
        />
        <Kennzahl
          label="Open Interest"
          wert={feldZahl(put, 'open_interest')}
          hinweis={`Volumen ${String(feldZahl(put, 'volume') ?? '–')}`}
        />
      </Kennzahlen>
      {warnungen.length > 0 && (
        <ul className="warnungen">
          {warnungen.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <Restfelder objekt={put} ausser={PUT_FELDER} />
    </Karte>
  );
}

export function Optionen({ dokument }: { dokument: ReportDocument }): ReactNode {
  const abschnitt = dokument.abschnitte['PUT_STRATEGIEN'];
  const inhalt = inhaltObjekt(abschnitt);
  const vorschlaege = objektliste(feldListe(inhalt, 'vorschlaege'));
  const spread = feldObjekt(inhalt, 'spread');
  return (
    <>
      <Karte titel="Put-Vorschläge">
        <Vorbehalte name="PUT_STRATEGIEN" abschnitt={abschnitt} />
        {inhalt !== null && (
          <p className="gedaempft">
            Status {beschrifte((feldText(inhalt, 'status') ?? '–').toLowerCase())}
            {feldZahl(inhalt, 'kurs') !== null && (
              <span> · Kurs {formatKurs(feldZahl(inhalt, 'kurs'))}</span>
            )}
            {feldText(inhalt, 'grund') !== null && <span> · {feldText(inhalt, 'grund')}</span>}
          </p>
        )}
        {vorschlaege.length === 0 && inhalt !== null && (
          <p className="zustand zustand-leer">Kein Vorschlag in diesem Lauf.</p>
        )}
        {vorschlaege.map((put, stelle) => (
          <Vorschlag key={stelle} put={put} rang={stelle + 1} />
        ))}
        <Restfelder
          objekt={inhalt}
          ausser={[
            'status',
            'kurs',
            'verfallstermin',
            'vorschlaege',
            'grund',
            'version',
            'spread',
            'spread_grund',
          ]}
        />
      </Karte>
      <Karte titel="Strukturvergleich (Put-Spread)">
        {spread === null ? (
          <p className="zustand zustand-leer">
            {feldText(inhalt, 'spread_grund') ?? 'Kein Vergleich in diesem Lauf.'}
          </p>
        ) : (
          <Restfelder objekt={spread} ausser={[]} />
        )}
      </Karte>
    </>
  );
}
