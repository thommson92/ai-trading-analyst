import type { ReactNode } from 'react';

import type { AnalysisRunDetail } from '@/lib/api';

export function Warnungen({ lauf }: { lauf: AnalysisRunDetail }): ReactNode {
  const eintraege: string[] = [];
  if (lauf.error_message !== null) eintraege.push(`Lauf meldet: ${lauf.error_message}`);
  if (lauf.module_errors > 0) {
    eintraege.push(
      `${String(lauf.module_errors)} Aktien sind an einem Modulfehler hängen geblieben.`,
    );
  }
  if (lauf.earnings_unknown > 0) {
    eintraege.push(
      `Bei ${String(lauf.earnings_unknown)} Kandidaten ist kein Berichtstermin bekannt — das ist kein belegter Nichttermin.`,
    );
  }
  return (
    <ul className="warnungen">
      {eintraege.length === 0 ? (
        <li className="keine">Keine.</li>
      ) : (
        eintraege.map((text) => <li key={text}>{text}</li>)
      )}
    </ul>
  );
}
