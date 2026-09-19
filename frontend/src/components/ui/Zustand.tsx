import type { ReactNode } from 'react';

// Drei Zustaende, die ueberall gleich aussehen -- und nie verwechselt
// werden: Ein Fehler ist kein leeres Ergebnis (api.ts).

export function Laedt({ was = 'Wird geladen …' }: { was?: string }): ReactNode {
  return <p className="zustand zustand-laedt">{was}</p>;
}

export function Leer({ children }: { children: ReactNode }): ReactNode {
  return <p className="zustand zustand-leer">{children}</p>;
}

export function Fehler({ children }: { children: ReactNode }): ReactNode {
  return (
    <p className="zustand zustand-fehler" role="alert">
      {children}
    </p>
  );
}

export function alsFehlertext(ursache: unknown): string {
  return ursache instanceof Error ? ursache.message : String(ursache);
}
