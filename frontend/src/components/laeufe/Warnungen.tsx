import type { ReactNode } from 'react';

import type { AnalysisRunDetail } from '@/lib/api';

export function Warnungen({ lauf }: { lauf: AnalysisRunDetail }): ReactNode {
  const eintraege: ReactNode[] = [];
  if (lauf.error_message !== null) eintraege.push(`Lauf meldet: ${lauf.error_message}`);
  if (lauf.module_errors > 0) {
    const fehler = lauf.processing_errors ?? [];
    eintraege.push(
      <>
        {lauf.module_errors} Aktien sind an einem Fehler hängen geblieben — deshalb gilt der Lauf
        als „teilweise abgeschlossen": Alle übrigen Aktien sind vollständig bewertet.
        {fehler.length > 0 && (
          <ul className="fehlerliste">
            {fehler.map((f) => (
              <li key={`${f.symbol}-${f.occurred_at}`}>
                <strong>{f.symbol}</strong>: {f.message}
              </li>
            ))}
          </ul>
        )}
      </>,
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
        eintraege.map((inhalt, stelle) => <li key={stelle}>{inhalt}</li>)
      )}
    </ul>
  );
}
