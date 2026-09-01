// Berichte als Tabelle -- in der Tagesuebersicht die Kandidaten eines Laufs,
// in der Historie die Laeufe einer Aktie.
//
// Sortiert wird hier nicht: Die Reihenfolge entscheidet, wer die Liste
// zeigt, und in der Historie kommt sie schon geordnet aus der API.

import Link from 'next/link';
import type { ReactNode } from 'react';

import type { ReportSummary } from '@/lib/api';
import { formatEmpfehlung, formatScore, formatZeitpunkt } from '@/lib/format';

export interface BerichtslisteProps {
  berichte: readonly ReportSummary[];
  mitDatum?: boolean;
}

export function Berichtsliste({ berichte, mitDatum = false }: BerichtslisteProps): ReactNode {
  return (
    <table>
      <thead>
        <tr>
          {mitDatum && <th scope="col">Erstellt</th>}
          <th scope="col">Symbol</th>
          <th scope="col">Empfehlung</th>
          <th scope="col" className="zahl">
            Swing
          </th>
          <th scope="col" className="zahl">
            Investment
          </th>
        </tr>
      </thead>
      <tbody>
        {berichte.map((bericht) => (
          <tr key={bericht.report_id}>
            {mitDatum && <td>{formatZeitpunkt(bericht.created_at)}</td>}
            <td>
              <Link href={`/bericht/?id=${bericht.report_id}`}>{bericht.symbol}</Link>
            </td>
            <td>{formatEmpfehlung(bericht.recommendation)}</td>
            <td className="zahl">{formatScore(bericht.swing_score)}</td>
            <td className="zahl">{formatScore(bericht.investment_score)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
