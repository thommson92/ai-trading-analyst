import type { ReactNode } from 'react';

/** Eine Flaeche mit optionalem Titel -- der Grundbaustein jeder Ansicht. */
export function Karte({
  titel,
  kopf,
  className,
  children,
}: {
  titel?: string;
  /** Rechts neben dem Titel, etwa ein Link oder eine Badge. */
  kopf?: ReactNode;
  className?: string;
  children: ReactNode;
}): ReactNode {
  return (
    <section className={className === undefined ? 'karte' : `karte ${className}`}>
      {(titel !== undefined || kopf !== undefined) && (
        <header className="karte-kopf">
          {titel !== undefined && <h2 className="karte-titel">{titel}</h2>}
          {kopf}
        </header>
      )}
      {children}
    </section>
  );
}
