'use client';

// Alle Aktien der Watchlist mit ihrem letzten Stand (ADR 0062). Gesucht und
// sortiert wird im Browser -- es sind zweihundert Zeilen, keine
// zwanzigtausend.

import { useEffect, useState, type ReactNode } from 'react';

import { Aktienliste } from '@/components/aktien/Aktienliste';
import { Karte } from '@/components/ui/Karte';
import { Fehler, Laedt, Leer, alsFehlertext } from '@/components/ui/Zustand';
import { getRun, listRuns, listStocks, type Aktieneintrag } from '@/lib/api';
import { datenmodus, type Datenbaum } from '@/lib/datenbaum';
import { setzeDatenbaumBeobachter } from '@/lib/api';

interface Stand {
  aktien: Aktieneintrag[];
  gesperrt: Set<string>;
  ohneChart: Set<string>;
}

async function ladeStand(baum: Datenbaum | null): Promise<Stand> {
  const [aktien, laeufe] = await Promise.all([listStocks(), listRuns({ limit: 1 })]);
  const neuester = laeufe.items[0];
  const gesperrt = new Set<string>();
  if (neuester !== undefined) {
    const detail = await getRun(neuester.id);
    for (const eintrag of detail.suppressed) gesperrt.add(eintrag.symbol);
  }
  return {
    aktien,
    gesperrt,
    // Nur ausserhalb des Servers gibt es ein Manifest; im eigenen Netz
    // beantwortet der Chart-Endpunkt die Frage selbst.
    ohneChart: new Set(baum?.manifest.stocks_without_chart ?? []),
  };
}

export default function AktienPage(): ReactNode {
  const [stand, setStand] = useState<Stand | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    let abgemeldet = false;
    ladeStand(datenmodus() === 'api' ? null : setzeDatenbaumBeobachter())
      .then((geladen) => {
        if (!abgemeldet) setStand(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) setFehler(alsFehlertext(ursache));
      });
    return () => {
      abgemeldet = true;
    };
  }, []);

  return (
    <main>
      <h1>Aktien</h1>
      {fehler !== null && <Fehler>Die Aktienliste ist nicht erreichbar: {fehler}</Fehler>}
      {stand === null && fehler === null && <Laedt />}
      {stand !== null && stand.aktien.length === 0 && (
        <Leer>Es gibt noch keine Aktien im Bestand.</Leer>
      )}
      {stand !== null && stand.aktien.length > 0 && (
        <Karte>
          <Aktienliste
            aktien={stand.aktien}
            gesperrt={stand.gesperrt}
            ohneChart={stand.ohneChart}
          />
        </Karte>
      )}
    </main>
  );
}
