import type { ReactNode } from 'react';

import { formatScore } from '@/lib/format';

/** Ein Score von 0 bis 10 als Zahl mit Balken; ohne Wert nur der Strich. */
export function ScoreAnzeige({ label, wert }: { label: string; wert: number | null }): ReactNode {
  const breite = wert === null ? 0 : Math.max(0, Math.min(100, wert * 10));
  return (
    <div className="score">
      <span className="score-label">{label}</span>
      <span className="score-wert">{formatScore(wert)}</span>
      <span className="score-balken" aria-hidden="true">
        <span className="score-fuellung" style={{ width: `${String(breite)}%` }} />
      </span>
    </div>
  );
}
