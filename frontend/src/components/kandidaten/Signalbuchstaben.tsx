import type { ReactNode } from 'react';

// Die Buchstaben A bis E sind die des Backtests (SIGNAL_BUCHSTABEN im
// Backend); der Titel erklaert sie beim Darueberfahren.
const BEDEUTUNG: Record<string, string | undefined> = {
  A: 'RSI kreuzt seinen Durchschnitt',
  B: 'Ausbruch über EMA 20',
  C: 'EMA 5 kreuzt EMA 20',
  D: 'RSI unter 30',
  E: 'kein Abwärtskreuz der EMAs',
};

export function Signalbuchstaben({ buchstaben }: { buchstaben: string | null }): ReactNode {
  if (buchstaben === null || buchstaben === '') {
    return <span className="fehlt">–</span>;
  }
  return (
    <span className="signalbuchstaben" aria-label={`Signale ${buchstaben}`}>
      {Array.from(buchstaben).map((buchstabe) => (
        <span key={buchstabe} className="signalbuchstabe" title={BEDEUTUNG[buchstabe]}>
          {buchstabe}
        </span>
      ))}
    </span>
  );
}
