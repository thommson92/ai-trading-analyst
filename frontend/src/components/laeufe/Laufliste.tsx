import Link from 'next/link';
import type { ReactNode } from 'react';

import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { AnalysisRun } from '@/lib/api';
import { LAUFSTATUS_TEXT, formatZeitpunkt } from '@/lib/format';
import { laufAdresse } from '@/lib/url';

const SPALTEN: readonly Spalte<AnalysisRun>[] = [
  {
    schluessel: 'start',
    titel: 'Lauf',
    kopf: true,
    render: (l) => <Link href={laufAdresse(l.id)}>{formatZeitpunkt(l.started_at)}</Link>,
    sortWert: (l) => l.started_at,
  },
  {
    schluessel: 'status',
    titel: 'Status',
    render: (l) => LAUFSTATUS_TEXT[l.status],
    sortWert: (l) => l.status,
  },
  {
    schluessel: 'aktien',
    titel: 'Gescreent',
    render: (l) => l.number_of_stocks,
    sortWert: (l) => l.number_of_stocks,
    zahl: true,
  },
  {
    schluessel: 'kandidaten',
    titel: 'Kandidaten',
    render: (l) => l.candidates_found,
    sortWert: (l) => l.candidates_found,
    zahl: true,
  },
  { schluessel: 'fehler', titel: 'Hinweis', render: (l) => l.error_message ?? '' },
];

export function Laufliste({
  laeufe,
  gewaehlt,
}: {
  laeufe: readonly AnalysisRun[];
  gewaehlt: string | null;
}): ReactNode {
  return (
    <Tabelle
      spalten={SPALTEN}
      zeilen={laeufe}
      schluesselVon={(l) => l.id}
      beschriftung="Alle Läufe"
      zeilenklasse={(l) => (l.id === gewaehlt ? 'gewaehlt' : undefined)}
    />
  );
}
