'use client';

// Der Rahmen um jede Ansicht (ADR 0063): links die Seitenleiste, oben die
// Kopfzeile mit dem Stand des Datenbaums und dem Themenschalter, darunter
// die Seite. Ein DOM fuer alle Breiten -- unter 64rem klappt die Leiste ein
// und legt sich auf Wunsch ueber den Inhalt.

import { useEffect, useRef, useState, type ReactNode } from 'react';

import { Seitenleiste } from './Seitenleiste';
import { Themenschalter } from './Themenschalter';

export function Seitenrahmen({
  stand,
  children,
}: {
  /** Der Stand des Datenbaums, wenn es einen gibt (ausserhalb des Servers). */
  stand?: ReactNode;
  children: ReactNode;
}): ReactNode {
  const [leisteOffen, setLeisteOffen] = useState(false);
  const rahmen = useRef<HTMLDivElement>(null);
  const menueknopf = useRef<HTMLButtonElement>(null);

  // Der Fokus folgt der Leiste: beim Oeffnen auf ihren ersten Eintrag, beim
  // Schliessen zurueck auf den Knopf. Sonst stuende er unter dem Overlay
  // oder, nach Escape, irgendwo.
  useEffect(() => {
    if (leisteOffen) {
      rahmen.current?.querySelector<HTMLElement>('.seitenleiste a')?.focus();
      return;
    }
    if (rahmen.current?.querySelector('.seitenleiste')?.contains(document.activeElement)) {
      menueknopf.current?.focus();
    }
  }, [leisteOffen]);

  useEffect(() => {
    if (!leisteOffen) {
      return;
    }
    function beiTaste(ereignis: KeyboardEvent): void {
      if (ereignis.key === 'Escape') {
        setLeisteOffen(false);
      }
    }
    window.addEventListener('keydown', beiTaste);
    return () => {
      window.removeEventListener('keydown', beiTaste);
    };
  }, [leisteOffen]);

  function schliessen(): void {
    setLeisteOffen(false);
  }

  return (
    <div className="rahmen" data-leiste-offen={leisteOffen ? 'true' : 'false'} ref={rahmen}>
      <Seitenleiste onNavigiert={schliessen} />
      <button
        type="button"
        className="leiste-hintergrund"
        aria-label="Navigation schließen"
        tabIndex={leisteOffen ? 0 : -1}
        onClick={schliessen}
      />
      <div className="rahmen-inhalt">
        <header className="kopfzeile">
          <button
            type="button"
            className="knopf-leicht menueknopf"
            aria-controls="seitenleiste"
            aria-expanded={leisteOffen}
            ref={menueknopf}
            onClick={() => {
              setLeisteOffen((offen) => !offen);
            }}
          >
            Menü
          </button>
          <div className="kopfzeile-stand">{stand}</div>
          <Themenschalter />
        </header>
        {children}
      </div>
    </div>
  );
}
