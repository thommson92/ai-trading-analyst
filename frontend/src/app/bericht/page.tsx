'use client';

// Die Detailansicht. Adressiert ueber `?id=` und nicht ueber ein
// Pfadsegment: Ein statischer Export muesste alle Kennungen zur Bauzeit
// kennen, und Berichte entstehen zur Laufzeit (ADR 0052).

import Link from 'next/link';
import { Suspense, useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from 'next/navigation';

import { Berichtsdokument } from '@/components/Berichtsdokument';
import { getReport, type JsonWert, type ReportDocument } from '@/lib/api';

function symbolAus(dokument: ReportDocument): string | null {
  const inhalt: JsonWert | undefined = dokument.abschnitte['SYMBOL_UND_UNTERNEHMEN']?.inhalt;
  if (inhalt === null || inhalt === undefined || typeof inhalt !== 'object') {
    return null;
  }
  if (Array.isArray(inhalt)) {
    return null;
  }
  const symbol = inhalt['symbol'];
  return typeof symbol === 'string' ? symbol : null;
}

function BerichtInhalt(): ReactNode {
  const suchparameter = useSearchParams();
  const id = suchparameter.get('id');
  const [dokument, setDokument] = useState<ReportDocument | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    if (id === null) {
      return;
    }
    let abgemeldet = false;
    getReport(id)
      .then((geladen) => {
        if (!abgemeldet) setDokument(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) {
          setFehler(ursache instanceof Error ? ursache.message : String(ursache));
        }
      });
    return () => {
      abgemeldet = true;
    };
  }, [id]);

  if (id === null) {
    return <p role="alert">Dieser Aufruf nennt keinen Bericht (`?id=` fehlt).</p>;
  }
  if (fehler !== null) {
    return <p role="alert">Der Bericht ist nicht abrufbar: {fehler}.</p>;
  }
  if (dokument === null) {
    return <p>Wird geladen …</p>;
  }

  const symbol = symbolAus(dokument);
  return (
    <>
      <h1>{symbol ?? 'Bericht'}</h1>
      <p>
        <Link href="/">← Tagesübersicht</Link>
        {symbol !== null && (
          <>
            {' · '}
            <Link href={`/aktie/?symbol=${encodeURIComponent(symbol)}`}>
              Historie dieser Aktie
            </Link>
          </>
        )}
      </p>
      <Berichtsdokument dokument={dokument} />
    </>
  );
}

export default function BerichtSeite(): ReactNode {
  return (
    <main>
      {/* `useSearchParams` braucht im statischen Export eine Suspense-Grenze:
          Die Seite wird vorab gebaut, die Parameter kennt erst der Browser. */}
      <Suspense fallback={<p>Wird geladen …</p>}>
        <BerichtInhalt />
      </Suspense>
    </main>
  );
}
