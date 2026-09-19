import Link from 'next/link';
import type { ReactNode } from 'react';

import { Signalbacktest } from '@/components/Signalbacktest';
import { Karte } from '@/components/ui/Karte';
import type { HorizontKennzahlen, Konfidenz, ReportDocument, SignalBacktest } from '@/lib/api';
import { buchstabenVon } from '@/lib/signale';
import { aktieAdresse } from '@/lib/url';

import { Vorbehalte } from '../Vorbehalte';
import {
  feldListe,
  feldText,
  feldZahl,
  inhaltListe,
  inhaltObjekt,
  objektliste,
  textliste,
  type JsonObjekt,
} from '../typwaechter';

const KONFIDENZEN: readonly Konfidenz[] = ['INSUFFICIENT_DATA', 'LOW_SAMPLE', 'NORMAL'];

// Kein Ersatzwert: Fehlt einem Horizont der Horizont selbst, eine Zaehlung
// oder die Konfidenz, kommt er nicht als "0 von 0, zu wenig Daten" in die
// Tabelle -- das saehe aus wie gemessen. Er wird gezaehlt und benannt; das
// Rohdokument zeigt ihn vollstaendig.
function horizont(h: JsonObjekt): HorizontKennzahlen | null {
  const horizon = feldZahl(h, 'horizon');
  const roh = feldZahl(h, 'raw_event_count');
  const gezaehlt = feldZahl(h, 'deduplicated_event_count');
  const konfidenz = KONFIDENZEN.find((k) => k === feldText(h, 'confidence'));
  if (horizon === null || roh === null || gezaehlt === null || konfidenz === undefined) {
    return null;
  }
  return {
    horizon,
    raw_event_count: roh,
    deduplicated_event_count: gezaehlt,
    hit_rate: feldZahl(h, 'hit_rate'),
    mean_return: feldZahl(h, 'mean_return'),
    median_return: feldZahl(h, 'median_return'),
    max_loss: feldZahl(h, 'max_loss'),
    drawdown: feldZahl(h, 'drawdown'),
    held_above_entry_rate: feldZahl(h, 'held_above_entry_rate'),
    confidence: konfidenz,
  };
}

export interface Signalstatistik {
  ergebnisse: SignalBacktest[];
  /** Horizontzeilen, denen Pflichtfelder fehlen -- nicht in der Tabelle. */
  unvollstaendig: number;
}

/** Die gespeicherte Signalstatistik in die Form der Backtest-Tabelle -- nur umgeformt, nichts gerechnet. */
export function signalstatistik(dokument: ReportDocument): Signalstatistik {
  let unvollstaendig = 0;
  const ergebnisse = objektliste(inhaltListe(dokument.abschnitte['SIGNALSTATISTIK'])).map((e) => {
    const typen = textliste(feldListe(e, 'signal_types'));
    const horizons: HorizontKennzahlen[] = [];
    for (const h of objektliste(feldListe(e, 'horizons'))) {
      const zeile = horizont(h);
      if (zeile === null) unvollstaendig += 1;
      else horizons.push(zeile);
    }
    return {
      signal_types: typen,
      letters: buchstabenVon(typen),
      signal_rule_version: feldText(e, 'signal_rule_version') ?? '–',
      evaluated_at: feldText(e, 'evaluated_at') ?? '',
      history_start: feldText(e, 'history_start') ?? '',
      history_end: feldText(e, 'history_end') ?? '',
      horizons,
    };
  });
  return { ergebnisse, unvollstaendig };
}

export function Backtest({ dokument }: { dokument: ReportDocument }): ReactNode {
  const abschnitt = dokument.abschnitte['SIGNALSTATISTIK'];
  const symbol = feldText(inhaltObjekt(dokument.abschnitte['SYMBOL_UND_UNTERNEHMEN']), 'symbol');
  const { ergebnisse, unvollstaendig } = signalstatistik(dokument);
  return (
    <Karte
      titel="Signalstatistik zum Zeitpunkt des Laufs"
      kopf={
        symbol === null ? undefined : (
          <Link href={aktieAdresse(symbol, { lauf: dokument.lauf_id })}>Chart und Episoden</Link>
        )
      }
    >
      <Vorbehalte name="SIGNALSTATISTIK" abschnitt={abschnitt} />
      <p className="gedaempft">
        Wie der Kurs dieser Aktie nach früheren Signalen lief — gerechnet im Lauf, nicht heute.
        {ergebnisse[0] !== undefined && (
          <span>
            {' '}
            Historie {ergebnisse[0].history_start.slice(0, 10)} bis{' '}
            {ergebnisse[0].history_end.slice(0, 10)}.
          </span>
        )}
      </p>
      {unvollstaendig > 0 && (
        <p className="gedaempft" role="note">
          {unvollstaendig} Horizontzeilen tragen nicht alle Pflichtfelder und stehen nicht in der
          Tabelle; das Rohdokument zeigt sie vollständig.
        </p>
      )}
      <div className="breit">
        <Signalbacktest ergebnisse={ergebnisse} />
      </div>
    </Karte>
  );
}
