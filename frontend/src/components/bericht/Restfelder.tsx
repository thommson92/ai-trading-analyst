import type { ReactNode } from 'react';

import { Wert } from '@/components/Berichtsdokument';
import { Aufklapper } from '@/components/ui/Aufklapper';
import { beschrifte } from '@/lib/format';

import type { JsonObjekt } from './typwaechter';

/**
 * Alles, was eine Darstellung nicht ausdruecklich verarbeitet hat. Die
 * Zusage "nichts verschwindet still" (ADR 0063, Entscheidung 7): Ein neues
 * Feld im Backend steht hier, bis jemand ihm einen Platz gibt.
 */
export function Restfelder({
  objekt,
  ausser,
}: {
  objekt: JsonObjekt | null;
  ausser: readonly string[];
}): ReactNode {
  if (objekt === null) return null;
  const rest = Object.entries(objekt).filter(([schluessel]) => !ausser.includes(schluessel));
  if (rest.length === 0) return null;
  return (
    <Aufklapper zusammenfassung={`Weitere Felder (${String(rest.length)})`}>
      <dl className="felder">
        {rest.map(([schluessel, inhalt]) => (
          <div key={schluessel}>
            <dt>{beschrifte(schluessel)}</dt>
            <dd>
              <Wert wert={inhalt} />
            </dd>
          </div>
        ))}
      </dl>
    </Aufklapper>
  );
}
