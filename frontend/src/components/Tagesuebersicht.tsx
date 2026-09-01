// Die Tagesuebersicht aus Doc 10, Paragraph 6.15.
//
// Reine Darstellung: Sie bekommt fertige Daten und zeigt sie. Sie holt
// nichts, rechnet nichts und ergaenzt nichts.

import type { ReactNode } from 'react';

import { Berichtsliste } from '@/components/Berichtsliste';
import type { AnalysisRun, AnalysisRunDetail, ReportSummary } from '@/lib/api';
import { formatZeitpunkt, LAUFSTATUS_TEXT, sortiereNachSwingScore } from '@/lib/format';

export interface TagesuebersichtProps {
  lauf: AnalysisRunDetail;
  letzterErfolg: AnalysisRun | null;
  kandidaten: readonly ReportSummary[];
}

export function Tagesuebersicht({
  lauf,
  letzterErfolg,
  kandidaten,
}: TagesuebersichtProps): ReactNode {
  const sortiert = sortiereNachSwingScore(kandidaten);
  return (
    <>
      <section aria-labelledby="lauf-titel">
        <h2 id="lauf-titel">Aktueller Lauf</h2>
        <dl className="kennzahlen">
          <div>
            <dt>Status</dt>
            <dd>{LAUFSTATUS_TEXT[lauf.status]}</dd>
          </div>
          <div>
            <dt>Gestartet</dt>
            <dd>{formatZeitpunkt(lauf.started_at)}</dd>
          </div>
          <div>
            <dt>Letzter erfolgreicher Lauf</dt>
            <dd>
              {letzterErfolg === null
                ? 'noch keiner'
                : formatZeitpunkt(letzterErfolg.completed_at ?? letzterErfolg.started_at)}
            </dd>
          </div>
          <div>
            <dt>Gescreente Aktien</dt>
            <dd>{lauf.number_of_stocks}</dd>
          </div>
          <div>
            <dt>Kandidaten</dt>
            <dd>{lauf.candidates_found}</dd>
          </div>
          <div>
            <dt>Wegen Berichtstermin ausgeschlossen</dt>
            <dd>{lauf.earnings_excluded}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="warnungen-titel">
        <h2 id="warnungen-titel">Warnungen und Datenprobleme</h2>
        <ul className="warnungen">
          {lauf.error_message !== null && <li>Lauf meldet: {lauf.error_message}</li>}
          {lauf.module_errors > 0 && (
            <li>{lauf.module_errors} Aktien sind an einem Modulfehler hängen geblieben.</li>
          )}
          {lauf.earnings_unknown > 0 && (
            <li>
              Bei {lauf.earnings_unknown} Kandidaten ist kein Berichtstermin bekannt — das ist
              kein belegter Nichttermin.
            </li>
          )}
          {lauf.error_message === null &&
            lauf.module_errors === 0 &&
            lauf.earnings_unknown === 0 && <li className="keine">Keine.</li>}
        </ul>
      </section>

      <section aria-labelledby="kandidaten-titel">
        <h2 id="kandidaten-titel">Kandidaten nach Swing-Score</h2>
        {sortiert.length === 0 ? (
          <p>Dieser Lauf hat keinen Kandidaten hervorgebracht.</p>
        ) : (
          <Berichtsliste berichte={sortiert} />
        )}
      </section>
    </>
  );
}
