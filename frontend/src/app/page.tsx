'use client';

// Die Tagesuebersicht holt ihre Daten im Browser: Das Dashboard ist ein
// statischer Export (ADR 0052), es gibt keinen Renderserver.

import { useEffect, useState, type ReactNode } from 'react';

import { Tagesuebersicht } from '@/components/Tagesuebersicht';
import {
  getRun,
  listRunReports,
  listRuns,
  type AnalysisRun,
  type AnalysisRunDetail,
  type ReportSummary,
} from '@/lib/api';

interface Uebersicht {
  lauf: AnalysisRunDetail;
  letzterErfolg: AnalysisRun | null;
  kandidaten: ReportSummary[];
}

async function ladeUebersicht(): Promise<Uebersicht | null> {
  const neueste = await listRuns({ limit: 1 });
  const neuester = neueste.items[0];
  if (neuester === undefined) {
    return null;
  }
  // Zwei verschiedene Laeufe, zwei Aufrufe: Der neueste sagt, wie es gerade
  // steht, der letzte erfolgreiche, wann zuletzt vollstaendig analysiert
  // wurde. Doc 10, Paragraph 6.15 verlangt beides.
  const [lauf, erfolgreiche, kandidaten] = await Promise.all([
    getRun(neuester.id),
    listRuns({ limit: 1, status: 'COMPLETED' }),
    listRunReports(neuester.id),
  ]);
  return { lauf, letzterErfolg: erfolgreiche.items[0] ?? null, kandidaten };
}

export default function HomePage(): ReactNode {
  const [uebersicht, setUebersicht] = useState<Uebersicht | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [laedt, setLaedt] = useState(true);

  useEffect(() => {
    let abgemeldet = false;
    ladeUebersicht()
      .then((geladen) => {
        if (!abgemeldet) {
          setUebersicht(geladen);
        }
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) {
          setFehler(ursache instanceof Error ? ursache.message : String(ursache));
        }
      })
      .finally(() => {
        if (!abgemeldet) {
          setLaedt(false);
        }
      });
    return () => {
      abgemeldet = true;
    };
  }, []);

  return (
    <main>
      <h1>Tagesübersicht</h1>
      {laedt && <p>Wird geladen …</p>}
      {fehler !== null && (
        <p role="alert">
          Die Analysedaten sind nicht erreichbar: {fehler}. Läuft der Dienst, und ist die
          Datenbank erreichbar?
        </p>
      )}
      {!laedt && fehler === null && uebersicht === null && (
        <p>Es gibt noch keinen Analyselauf.</p>
      )}
      {uebersicht !== null && (
        <Tagesuebersicht
          lauf={uebersicht.lauf}
          letzterErfolg={uebersicht.letzterErfolg}
          kandidaten={uebersicht.kandidaten}
        />
      )}
    </main>
  );
}
