"use client";

// Der Rahmen um jede Ansicht (ADR 0063): links die Seitenleiste, oben die
// Kopfzeile mit dem Stand des Datenbaums und dem Themenschalter, darunter
// die Seite. Ein DOM fuer alle Breiten -- unter 64rem klappt die Leiste ein
// und legt sich auf Wunsch ueber den Inhalt.

import { useEffect, useState, type ReactNode } from "react";

import { Seitenleiste } from "./Seitenleiste";
import { Themenschalter } from "./Themenschalter";

export function Seitenrahmen({
  stand,
  children,
}: {
  /** Der Stand des Datenbaums, wenn es einen gibt (ausserhalb des Servers). */
  stand?: ReactNode;
  children: ReactNode;
}): ReactNode {
  const [leisteOffen, setLeisteOffen] = useState(false);

  useEffect(() => {
    if (!leisteOffen) {
      return;
    }
    function beiTaste(ereignis: KeyboardEvent): void {
      if (ereignis.key === "Escape") {
        setLeisteOffen(false);
      }
    }
    window.addEventListener("keydown", beiTaste);
    return () => {
      window.removeEventListener("keydown", beiTaste);
    };
  }, [leisteOffen]);

  function schliessen(): void {
    setLeisteOffen(false);
  }

  return (
    <div className="rahmen" data-leiste-offen={leisteOffen ? "true" : "false"}>
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
