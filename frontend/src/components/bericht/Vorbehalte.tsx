import type { ReactNode } from 'react';

import type { Berichtsabschnitt } from '@/lib/api';
import { ABSCHNITT_TEXT } from '@/lib/format';

const ART_TEXT: Record<string, string | undefined> = {
  FEHLT: 'fehlt',
  EINGESCHRAENKT: 'eingeschränkt',
};

/** Die Vorbehalte eines Abschnitts -- ueber seinem Inhalt, nicht darunter. */
export function Vorbehalte({
  name,
  abschnitt,
}: {
  name: string;
  abschnitt: Berichtsabschnitt | undefined;
}): ReactNode {
  if (abschnitt === undefined) {
    return (
      <p className="zustand zustand-leer">{ABSCHNITT_TEXT[name] ?? name}: nicht im Bericht.</p>
    );
  }
  return (
    <>
      {!abschnitt.verfuegbar && (
        <p className="zustand zustand-leer">{ABSCHNITT_TEXT[name] ?? name}: nicht verfügbar.</p>
      )}
      {abschnitt.vorbehalte.map((vorbehalt, stelle) => (
        <p className="vorbehalt" key={stelle}>
          <strong>{ART_TEXT[vorbehalt.art] ?? vorbehalt.art}:</strong> {vorbehalt.grund}
        </p>
      ))}
    </>
  );
}
