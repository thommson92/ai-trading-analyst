// Ein Lauf vollstaendig: Kennzahlen, Warnungen, Kandidaten, Sperrliste.
// Geteilt zwischen Uebersicht (der neueste Lauf) und Tageslaeufen (ein
// gewaehlter Lauf) -- eine Darstellung, zwei Seiten.

import type { ReactNode } from 'react';

import { Kandidatenkarte } from '@/components/kandidaten/Kandidatenkarte';
import { Karte } from '@/components/ui/Karte';
import { Leer } from '@/components/ui/Zustand';
import type { AnalysisRun, AnalysisRunDetail, ReportSummary } from '@/lib/api';

import { Laufkennzahlen } from './Laufkennzahlen';
import { Sperrliste } from './Sperrliste';
import { Warnungen } from './Warnungen';

export function Laufdetail({
  lauf,
  letzterErfolg,
  kandidaten,
}: {
  lauf: AnalysisRunDetail;
  letzterErfolg?: AnalysisRun | null;
  kandidaten: readonly ReportSummary[];
}): ReactNode {
  return (
    <div className="laufdetail">
      <Karte titel="Lauf">
        <Laufkennzahlen lauf={lauf} letzterErfolg={letzterErfolg} />
      </Karte>
      <Karte titel="Warnungen und Datenprobleme">
        <Warnungen lauf={lauf} />
      </Karte>
      <Karte titel="Kandidaten nach Swing-Score">
        {kandidaten.length === 0 ? (
          <Leer>Dieser Lauf hat keinen Kandidaten hervorgebracht.</Leer>
        ) : (
          <div className="kandidatenraster">
            {kandidaten.map((bericht) => (
              <Kandidatenkarte key={bericht.report_id} bericht={bericht} />
            ))}
          </div>
        )}
      </Karte>
      <Sperrliste gesperrt={lauf.suppressed} fensterTage={lauf.suppression_window_days} />
    </div>
  );
}
