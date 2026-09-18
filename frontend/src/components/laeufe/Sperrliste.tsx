import Link from 'next/link';
import type { ReactNode } from 'react';

import { Aufklapper } from '@/components/ui/Aufklapper';
import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { GesperrtesSymbol } from '@/lib/api';
import { formatZeitpunkt } from '@/lib/format';
import { aktieAdresse, laufAdresse } from '@/lib/url';

const SPALTEN: readonly Spalte<GesperrtesSymbol>[] = [
  {
    schluessel: 'symbol',
    titel: 'Symbol',
    kopf: true,
    render: (s) => <Link href={aktieAdresse(s.symbol)}>{s.symbol}</Link>,
    sortWert: (s) => s.symbol,
  },
  {
    schluessel: 'wann',
    titel: 'Zuletzt voll analysiert',
    render: (s) => formatZeitpunkt(s.blocking_evaluated_at),
    sortWert: (s) => s.blocking_evaluated_at,
  },
  {
    schluessel: 'lauf',
    titel: 'Sperrender Lauf',
    render: (s) => <Link href={laufAdresse(s.blocking_run_id)}>zum Lauf</Link>,
  },
];

/**
 * Was die Wiederholsperre aus dem Lauf genommen hat (ADR 0054) -- rekonstruiert
 * (ADR 0062), und die Zusammenfassung sagt das.
 */
export function Sperrliste({
  gesperrt,
  fensterTage,
}: {
  gesperrt: readonly GesperrtesSymbol[];
  fensterTage: number | null;
}): ReactNode {
  if (fensterTage === null) {
    return null;
  }
  return (
    <Aufklapper
      zusammenfassung={`${String(gesperrt.length)} Symbole durch die Wiederholsperre übersprungen (Fenster ${String(fensterTage)} Tage, abgeleitet)`}
    >
      {gesperrt.length === 0 ? (
        <p className="gedaempft">Kein Symbol war im Sperrfenster.</p>
      ) : (
        <Tabelle
          spalten={SPALTEN}
          zeilen={gesperrt}
          schluesselVon={(s) => s.symbol}
          beschriftung="Übersprungene Symbole"
        />
      )}
    </Aufklapper>
  );
}
