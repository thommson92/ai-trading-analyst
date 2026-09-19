'use client';

// Alle Tageslaeufe, und einer davon vollstaendig. Die Wahl steht in der
// Adresse (`?id=`), damit ein Lauf verlinkbar bleibt; ohne Wahl gilt der
// neueste.

import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState, type ReactNode } from 'react';

import { Laufdetail } from '@/components/laeufe/Laufdetail';
import { Laufliste } from '@/components/laeufe/Laufliste';
import { Karte } from '@/components/ui/Karte';
import { Fehler, Laedt, Leer, alsFehlertext } from '@/components/ui/Zustand';
import {
  getRun,
  listRunReports,
  listRuns,
  type AnalysisRun,
  type AnalysisRunDetail,
  type ReportSummary,
} from '@/lib/api';

interface Auswahl {
  lauf: AnalysisRunDetail;
  kandidaten: ReportSummary[];
}

function LaeufeInhalt(): ReactNode {
  const gewuenscht = useSearchParams().get('id');
  const [laeufe, setLaeufe] = useState<AnalysisRun[] | null>(null);
  const [gesamt, setGesamt] = useState(0);
  const [auswahl, setAuswahl] = useState<Auswahl | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [laedtAuswahl, setLaedtAuswahl] = useState(false);

  useEffect(() => {
    let abgemeldet = false;
    // Die groesste Seite der API; ausserhalb liegt ohnehin die ganze Liste.
    listRuns({ limit: 100 })
      .then((seite) => {
        if (!abgemeldet) {
          setLaeufe(seite.items);
          setGesamt(seite.total);
        }
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) setFehler(alsFehlertext(ursache));
      });
    return () => {
      abgemeldet = true;
    };
  }, []);

  const gewaehlt = gewuenscht ?? laeufe?.[0]?.id ?? null;

  useEffect(() => {
    if (gewaehlt === null) return;
    let abgemeldet = false;
    setLaedtAuswahl(true);
    setFehler(null);
    Promise.all([getRun(gewaehlt), listRunReports(gewaehlt)])
      .then(([lauf, kandidaten]) => {
        if (!abgemeldet) setAuswahl({ lauf, kandidaten });
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) setFehler(alsFehlertext(ursache));
      })
      .finally(() => {
        if (!abgemeldet) setLaedtAuswahl(false);
      });
    return () => {
      abgemeldet = true;
    };
  }, [gewaehlt]);

  return (
    <main>
      <h1>Tagesläufe</h1>
      {fehler !== null && <Fehler>Die Läufe sind nicht erreichbar: {fehler}</Fehler>}
      {laeufe === null && fehler === null && <Laedt />}
      {laeufe !== null && laeufe.length === 0 && <Leer>Es gibt noch keinen Analyselauf.</Leer>}
      {laeufe !== null && laeufe.length > 0 && (
        <Karte titel="Alle Läufe">
          {gesamt > laeufe.length && (
            <p className="gedaempft">
              Die {laeufe.length} jüngsten von {gesamt} Läufen. Ältere sind hier nicht aufgeführt;
              ein älterer Lauf bleibt über seine Adresse (?id=) erreichbar.
            </p>
          )}
          <Laufliste laeufe={laeufe} gewaehlt={gewaehlt} />
        </Karte>
      )}
      {laedtAuswahl && <Laedt was="Lauf wird geladen …" />}
      {auswahl !== null && auswahl.lauf.id === gewaehlt && (
        <Laufdetail lauf={auswahl.lauf} kandidaten={auswahl.kandidaten} />
      )}
    </main>
  );
}

export default function LaeufePage(): ReactNode {
  return (
    <Suspense fallback={<Laedt />}>
      <LaeufeInhalt />
    </Suspense>
  );
}
