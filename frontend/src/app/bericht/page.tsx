'use client';

// Die Berichtsseite laedt das Dokument im Browser (ADR 0052) und reicht es
// an die Berichtsseite-Komponente weiter, die Kopf und Reiter zeigt.

import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState, type ReactNode } from 'react';

import { Berichtsseite } from '@/components/bericht/Berichtsseite';
import { Fehler, Laedt, alsFehlertext } from '@/components/ui/Zustand';
import { getReport, type ReportDocument } from '@/lib/api';

function BerichtInhalt(): ReactNode {
  const id = useSearchParams().get('id');
  const [dokument, setDokument] = useState<ReportDocument | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    if (id === null) return;
    let abgemeldet = false;
    // Sonst staende beim Wechsel der Kennung (Browser-Zurueck) der alte
    // Bericht oder ein alter Fehler neben dem neuen Kopf.
    setDokument(null);
    setFehler(null);
    getReport(id)
      .then((geladen) => {
        if (!abgemeldet) setDokument(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) setFehler(alsFehlertext(ursache));
      });
    return () => {
      abgemeldet = true;
    };
  }, [id]);

  if (id === null) {
    return <Fehler>Dieser Aufruf nennt keinen Bericht (?id= fehlt).</Fehler>;
  }
  return (
    <>
      {fehler !== null && <Fehler>Der Bericht ist nicht erreichbar: {fehler}</Fehler>}
      {dokument === null && fehler === null && <Laedt was="Bericht wird geladen …" />}
      {dokument !== null && <Berichtsseite dokument={dokument} />}
    </>
  );
}

export default function BerichtPage(): ReactNode {
  return (
    <main>
      <Suspense fallback={<Laedt />}>
        <BerichtInhalt />
      </Suspense>
    </main>
  );
}
