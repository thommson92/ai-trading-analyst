'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

/**
 * Die Hauptbereiche des Dashboards, als Pfad **unter der Wurzel**. Die Liste
 * waechst mit den Phasen des Redesigns (ADR 0063); ein Eintrag steht hier
 * erst, wenn seine Seite existiert.
 *
 * Ohne fuehrenden Schraegstrich, damit das `href` unten mit dem konstanten
 * Praefix `/` beginnt, auf das `sicherheitsheader.test.ts` besteht.
 */
export const BEREICHE: readonly { pfad: string; titel: string }[] = [
  { pfad: '', titel: 'Übersicht' },
  { pfad: 'backtests/', titel: 'Backtests' },
];

/** `/backtests` und `/backtests/` sind dieselbe Seite (`trailingSlash: true`). */
function normalisiert(pfad: string): string {
  return pfad.endsWith('/') ? pfad : `${pfad}/`;
}

export function Seitenleiste({ onNavigiert }: { onNavigiert: () => void }): ReactNode {
  const aktuell = normalisiert(usePathname());
  return (
    <aside className="seitenleiste" id="seitenleiste">
      <Link href="/" className="seitenleiste-titel" onClick={onNavigiert}>
        AI Trading Analyst
      </Link>
      <nav aria-label="Hauptnavigation">
        <ul>
          {BEREICHE.map((bereich) => {
            const aktiv = aktuell === normalisiert(`/${bereich.pfad}`);
            return (
              <li key={bereich.pfad}>
                <Link
                  href={`/${bereich.pfad}`}
                  aria-current={aktiv ? 'page' : undefined}
                  onClick={onNavigiert}
                >
                  {bereich.titel}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <p className="seitenleiste-fuss">Persönliches Analyse-Dashboard</p>
    </aside>
  );
}
