import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/Badge';
import type { PutVorschlag as PutVorschlagDaten } from '@/lib/api';
import { LIQUIDITAET_TEXT, formatDatum, formatKurs, formatProzent } from '@/lib/format';

/**
 * Der beste Put-Vorschlag des Berichts -- Strike, Verfall, Praemie je Aktie,
 * annualisierte Rendite. Ohne Vorschlag steht der Grund, nicht nichts.
 */
export function PutVorschlag({
  vorschlag,
  status,
  grund,
}: {
  vorschlag: PutVorschlagDaten | null;
  status: string | null;
  grund: string | null;
}): ReactNode {
  if (vorschlag === null) {
    return (
      <div className="hinweis">
        <span className="hinweis-label">Put-Vorschlag</span>
        <span className="fehlt">
          {status === null ? 'keine Optionsdaten' : (grund ?? 'kein Vorschlag')}
        </span>
      </div>
    );
  }
  return (
    <div className="hinweis">
      <span className="hinweis-label">Put-Vorschlag</span>
      <span className="hinweis-wert">
        <strong>Strike {formatKurs(vorschlag.strike)}</strong> · Verfall{' '}
        {formatDatum(vorschlag.expiration)} ({vorschlag.days_to_expiration} Tage) · Prämie{' '}
        {formatKurs(vorschlag.premium)} je Aktie
        {vorschlag.annualized_return !== null && (
          <span> · {formatProzent(vorschlag.annualized_return)} p. a.</span>
        )}
        {vorschlag.liquidity !== null && (
          <Badge variante="neutral">
            {LIQUIDITAET_TEXT[vorschlag.liquidity] ?? vorschlag.liquidity}
          </Badge>
        )}
        {vorschlag.earnings_within_term === true && (
          <Badge variante="warnung">Berichtstermin in der Laufzeit</Badge>
        )}
      </span>
    </div>
  );
}
