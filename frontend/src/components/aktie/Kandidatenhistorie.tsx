import Link from 'next/link';
import type { ReactNode } from 'react';

import { Empfehlungsbadge } from '@/components/kandidaten/Empfehlungsbadge';
import { Signalbuchstaben } from '@/components/kandidaten/Signalbuchstaben';
import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { ReportSummary } from '@/lib/api';
import { EARNINGS_TEXT, formatKurs, formatScore, formatZeitpunkt } from '@/lib/format';
import { berichtAdresse, laufAdresse } from '@/lib/url';

const SPALTEN: readonly Spalte<ReportSummary>[] = [
  {
    schluessel: 'datum',
    titel: 'Lauf',
    kopf: true,
    render: (b) => <Link href={berichtAdresse(b.report_id)}>{formatZeitpunkt(b.created_at)}</Link>,
    sortWert: (b) => b.created_at,
  },
  {
    schluessel: 'kurs',
    titel: 'Kurs',
    zahl: true,
    render: (b) => formatKurs(b.close),
    sortWert: (b) => b.close,
  },
  {
    schluessel: 'signale',
    titel: 'Signale',
    render: (b) => <Signalbuchstaben buchstaben={b.signal_letters} />,
  },
  {
    schluessel: 'empfehlung',
    titel: 'Empfehlung',
    render: (b) => <Empfehlungsbadge stufe={b.recommendation} />,
    sortWert: (b) => b.recommendation,
  },
  {
    schluessel: 'swing',
    titel: 'Swing',
    zahl: true,
    render: (b) => formatScore(b.swing_score),
    sortWert: (b) => b.swing_score,
  },
  {
    schluessel: 'investment',
    titel: 'Investment',
    zahl: true,
    render: (b) => formatScore(b.investment_score),
    sortWert: (b) => b.investment_score,
  },
  {
    schluessel: 'earnings',
    titel: 'Berichtstermin',
    render: (b) =>
      b.earnings_status === null
        ? '–'
        : `${EARNINGS_TEXT[b.earnings_status]}${b.earnings_next_date === null ? '' : ` (${b.earnings_next_date})`}`,
  },
  {
    schluessel: 'put',
    titel: 'Put',
    render: (b) =>
      b.put_suggestion === null
        ? (b.options_reason ?? '–')
        : `Strike ${formatKurs(b.put_suggestion.strike)} · ${formatKurs(b.put_suggestion.premium)}`,
  },
  {
    schluessel: 'lauf',
    titel: '',
    render: (b) => <Link href={laufAdresse(b.analysis_run_id)}>Tageslauf</Link>,
  },
];

/** Jeder Lauf, in dem die Aktie Kandidat war -- mit dem damaligen Stand (ADR 0062). */
export function Kandidatenhistorie({
  berichte,
}: {
  berichte: readonly ReportSummary[];
}): ReactNode {
  return (
    <Tabelle
      spalten={SPALTEN}
      zeilen={berichte}
      schluesselVon={(b) => b.report_id}
      sortierung={{ schluessel: 'datum', richtung: 'ab' }}
      beschriftung="Kandidatenhistorie"
    />
  );
}
