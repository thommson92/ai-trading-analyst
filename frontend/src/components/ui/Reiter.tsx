'use client';

// Reiter nach dem WAI-ARIA-Muster: role=tablist, Pfeiltasten, ein Panel.
// Welcher Reiter offen ist, entscheidet die Seite -- meist aus `?tab=`, damit
// ein Reiter verlinkbar bleibt.

import type { KeyboardEvent, ReactNode } from 'react';

export interface Reiterdefinition {
  id: string;
  titel: string;
  /** Eine kleine Zahl oder Markierung neben dem Titel. */
  zusatz?: ReactNode;
}

export function Reiter({
  reiter,
  aktiv,
  onWechsel,
  beschriftung,
  children,
}: {
  reiter: readonly Reiterdefinition[];
  aktiv: string;
  onWechsel: (id: string) => void;
  beschriftung: string;
  children: ReactNode;
}): ReactNode {
  function beiTaste(ereignis: KeyboardEvent<HTMLButtonElement>, stelle: number): void {
    const schritt = ereignis.key === 'ArrowRight' ? 1 : ereignis.key === 'ArrowLeft' ? -1 : 0;
    if (schritt === 0) return;
    ereignis.preventDefault();
    const naechster = reiter[(stelle + schritt + reiter.length) % reiter.length];
    if (naechster !== undefined) {
      onWechsel(naechster.id);
      ereignis.currentTarget.parentElement
        ?.querySelector<HTMLButtonElement>(`[data-reiter="${naechster.id}"]`)
        ?.focus();
    }
  }
  return (
    <>
      <div className="reiter" role="tablist" aria-label={beschriftung}>
        {reiter.map((eintrag, stelle) => (
          <button
            key={eintrag.id}
            type="button"
            role="tab"
            id={`reiter-${eintrag.id}`}
            data-reiter={eintrag.id}
            aria-selected={eintrag.id === aktiv}
            aria-controls={`panel-${eintrag.id}`}
            tabIndex={eintrag.id === aktiv ? 0 : -1}
            onClick={() => {
              onWechsel(eintrag.id);
            }}
            onKeyDown={(ereignis) => {
              beiTaste(ereignis, stelle);
            }}
          >
            {eintrag.titel}
            {eintrag.zusatz !== undefined && (
              <span className="reiter-zusatz">{eintrag.zusatz}</span>
            )}
          </button>
        ))}
      </div>
      <div
        className="reiterinhalt"
        role="tabpanel"
        id={`panel-${aktiv}`}
        aria-labelledby={`reiter-${aktiv}`}
      >
        {children}
      </div>
    </>
  );
}
