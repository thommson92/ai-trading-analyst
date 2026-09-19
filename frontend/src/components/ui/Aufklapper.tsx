import type { ReactNode } from 'react';

/** Ein zugeklappter Abschnitt; die Zusammenfassung bleibt beim Scrollen stehen. */
export function Aufklapper({
  zusammenfassung,
  offen = false,
  children,
}: {
  zusammenfassung: ReactNode;
  offen?: boolean;
  children: ReactNode;
}): ReactNode {
  return (
    <details className="aufklapper" open={offen}>
      <summary>{zusammenfassung}</summary>
      <div className="aufklapper-inhalt">{children}</div>
    </details>
  );
}
