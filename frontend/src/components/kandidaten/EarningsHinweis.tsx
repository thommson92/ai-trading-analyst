import type { ReactNode } from 'react';

import { Badge, type BadgeVariante } from '@/components/ui/Badge';
import type { EarningsStatus } from '@/lib/api';
import { EARNINGS_TEXT, formatDatum } from '@/lib/format';

const VARIANTE: Record<EarningsStatus, BadgeVariante> = {
  EARNINGS_CLEAR: 'neutral',
  EARNINGS_EXCLUDED: 'verlust',
  UNKNOWN: 'warnung',
};

/**
 * Wann der naechste Berichtstermin ist -- und ob er bekannt ist. "Unbekannt"
 * bekommt eine Warnfarbe: Es ist kein belegter Nichttermin (ADR 0020).
 */
export function EarningsHinweis({
  status,
  termin,
  kerzen,
}: {
  status: EarningsStatus | null;
  termin: string | null;
  kerzen: number | null;
}): ReactNode {
  if (status === null) {
    return (
      <div className="hinweis">
        <span className="hinweis-label">Berichtstermin</span>
        <span className="fehlt">nicht geprüft</span>
      </div>
    );
  }
  return (
    <div className="hinweis">
      <span className="hinweis-label">Berichtstermin</span>
      <span className="hinweis-wert">
        <Badge variante={VARIANTE[status]}>{EARNINGS_TEXT[status]}</Badge>
        {termin !== null && <span> am {formatDatum(termin)}</span>}
        {kerzen !== null && <span className="gedaempft"> · in {kerzen} Kerzen</span>}
      </span>
    </div>
  );
}
