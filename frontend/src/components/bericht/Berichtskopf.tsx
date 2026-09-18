// Der Kopf des Kandidatenberichts (ADR 0063, Entscheidung 7): was auf einen
// Blick zaehlt -- Kurs, Berichtstermin, Put-Vorschlag; darunter Empfehlung,
// Scores, Signale. Gelesen aus den Abschnitten des eingefrorenen Dokuments.

import Link from 'next/link';
import type { ReactNode } from 'react';

import { EarningsHinweis } from '@/components/kandidaten/EarningsHinweis';
import { Empfehlungsbadge } from '@/components/kandidaten/Empfehlungsbadge';
import { PutVorschlag } from '@/components/kandidaten/PutVorschlag';
import { ScoreAnzeige } from '@/components/kandidaten/ScoreAnzeige';
import { Signalbuchstaben } from '@/components/kandidaten/Signalbuchstaben';
import { Badge } from '@/components/ui/Badge';
import type {
  EarningsStatus,
  PutVorschlag as PutDaten,
  Recommendation,
  ReportDocument,
} from '@/lib/api';
import { FEHLSIGNALRISIKO_TEXT, formatKurs, formatZeitpunkt } from '@/lib/format';
import { buchstabenVon } from '@/lib/signale';
import { aktieAdresse, laufAdresse } from '@/lib/url';

import {
  feldListe,
  feldObjekt,
  feldText,
  feldWahrheit,
  feldZahl,
  inhaltListe,
  inhaltObjekt,
  objektliste,
} from './typwaechter';

const EMPFEHLUNGEN: readonly Recommendation[] = [
  'STRONG_CANDIDATE',
  'CANDIDATE',
  'WATCH',
  'AVOID_FOR_NOW',
  'INSUFFICIENT_DATA',
];
const EARNINGS: readonly EarningsStatus[] = ['EARNINGS_CLEAR', 'EARNINGS_EXCLUDED', 'UNKNOWN'];

function alsEmpfehlung(wert: string | null): Recommendation | null {
  return EMPFEHLUNGEN.find((stufe) => stufe === wert) ?? null;
}

function alsEarnings(wert: string | null): EarningsStatus | null {
  return EARNINGS.find((status) => status === wert) ?? null;
}

function ersterPut(dokument: ReportDocument): PutDaten | null {
  const puts = inhaltObjekt(dokument.abschnitte['PUT_STRATEGIEN']);
  const erster = objektliste(feldListe(puts, 'vorschlaege'))[0] ?? null;
  const strike = feldZahl(erster, 'strike');
  const expiration = feldText(erster, 'expiration');
  const tage = feldZahl(erster, 'days_to_expiration');
  const praemie = feldZahl(erster, 'premium');
  if (strike === null || expiration === null || tage === null || praemie === null) return null;
  return {
    strike,
    expiration,
    days_to_expiration: tage,
    premium: praemie,
    annualized_return: feldZahl(erster, 'annualized_return'),
    distance_to_price_pct: feldZahl(erster, 'distance_to_price_pct'),
    liquidity: feldText(erster, 'liquidity'),
    earnings_within_term: feldWahrheit(erster, 'earnings_within_term'),
  };
}

export function Berichtskopf({ dokument }: { dokument: ReportDocument }): ReactNode {
  const a = dokument.abschnitte;
  const unternehmen = inhaltObjekt(a['SYMBOL_UND_UNTERNEHMEN']);
  const symbol = feldText(unternehmen, 'symbol') ?? '?';
  const lage = inhaltObjekt(a['TECHNISCHE_LAGE']);
  const deterministisch = feldObjekt(lage, 'deterministisch');
  const einordnung = feldObjekt(lage, 'einordnung');
  const earnings = inhaltObjekt(a['EARNINGS_STATUS']);
  const puts = inhaltObjekt(a['PUT_STRATEGIEN']);
  const signale = objektliste(inhaltListe(a['TECHNISCHE_SIGNALE']))
    .map((eintrag) => feldText(eintrag, 'signal_type'))
    .filter((typ): typ is string => typ !== null);
  const buchstaben = buchstabenVon(signale);
  const fehlsignal = feldText(einordnung, 'false_signal_risk');

  return (
    <header className="berichtskopf">
      <div className="berichtskopf-zeile">
        <div>
          <h1 className="berichtskopf-symbol">{symbol}</h1>
          <p className="berichtskopf-name">
            {feldText(unternehmen, 'unternehmen') ?? 'Unternehmen unbekannt'}
            {feldText(unternehmen, 'boerse') !== null && (
              <span> · {feldText(unternehmen, 'boerse')}</span>
            )}
          </p>
          <p className="gedaempft">
            Bericht vom {formatZeitpunkt(dokument.erstellt_am)} ·{' '}
            <Link href={laufAdresse(dokument.lauf_id)}>zum Lauf</Link> ·{' '}
            <Link href={aktieAdresse(symbol, { lauf: dokument.lauf_id })}>zur Aktie</Link>
          </p>
        </div>
        <span className="berichtskopf-kurs">{formatKurs(feldZahl(deterministisch, 'close'))}</span>
      </div>
      <div className="berichtskopf-reihe">
        <EarningsHinweis
          status={alsEarnings(feldText(earnings, 'status'))}
          termin={feldText(earnings, 'next_earnings_date')}
          kerzen={feldZahl(earnings, 'candles_until_earnings')}
        />
        <PutVorschlag
          vorschlag={ersterPut(dokument)}
          status={feldText(puts, 'status')}
          grund={feldText(puts, 'grund')}
        />
      </div>
      <div className="berichtskopf-reihe berichtskopf-zweite">
        <Empfehlungsbadge stufe={alsEmpfehlung(feldText(inhaltObjekt(a['EMPFEHLUNG']), 'stufe'))} />
        <ScoreAnzeige label="Swing" wert={feldZahl(inhaltObjekt(a['SWING_SCORE']), 'value')} />
        <ScoreAnzeige
          label="Investment"
          wert={feldZahl(inhaltObjekt(a['INVESTMENT_SCORE']), 'value')}
        />
        <Signalbuchstaben buchstaben={buchstaben === '' ? null : buchstaben} />
        {fehlsignal !== null && (
          <Badge variante={fehlsignal === 'HIGH' ? 'warnung' : 'neutral'}>
            Fehlsignalrisiko {FEHLSIGNALRISIKO_TEXT[fehlsignal] ?? fehlsignal}
          </Badge>
        )}
      </div>
    </header>
  );
}
