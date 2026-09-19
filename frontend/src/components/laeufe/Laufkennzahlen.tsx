import type { ReactNode } from 'react';

import { Kennzahl, Kennzahlen } from '@/components/ui/Kennzahl';
import type { AnalysisRun, AnalysisRunDetail } from '@/lib/api';
import { LAUFSTATUS_TEXT, formatZeitpunkt } from '@/lib/format';

export function Laufkennzahlen({
  lauf,
  letzterErfolg,
}: {
  lauf: AnalysisRunDetail;
  letzterErfolg?: AnalysisRun | null | undefined;
}): ReactNode {
  return (
    <Kennzahlen>
      <Kennzahl label="Status" wert={LAUFSTATUS_TEXT[lauf.status]} />
      <Kennzahl
        label="Gestartet"
        wert={formatZeitpunkt(lauf.started_at)}
        hinweis={
          letzterErfolg === undefined
            ? undefined
            : letzterErfolg === null
              ? 'noch kein erfolgreicher Lauf'
              : letzterErfolg.id === lauf.id
                ? 'der letzte erfolgreiche Lauf'
                : `letzter erfolgreicher: ${formatZeitpunkt(letzterErfolg.completed_at ?? letzterErfolg.started_at)}`
        }
      />
      <Kennzahl label="Gescreente Aktien" wert={lauf.number_of_stocks} />
      <Kennzahl label="Kandidaten" wert={lauf.candidates_found} betont />
      <Kennzahl label="Wegen Berichtstermin ausgeschlossen" wert={lauf.earnings_excluded} />
      <Kennzahl
        label="Durch Wiederholsperre übersprungen"
        wert={lauf.suppression_window_days === null ? '–' : lauf.suppressed.length}
        hinweis={lauf.suppression_window_days === null ? 'nicht gerechnet' : 'abgeleitet'}
      />
    </Kennzahlen>
  );
}
