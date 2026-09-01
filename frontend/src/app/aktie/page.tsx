'use client';

// Die Analysehistorie einer Aktie (US-010): jeder Lauf, an dem sie Kandidat
// war. Adressiert ueber `?symbol=`, aus demselben Grund wie die
// Detailansicht (ADR 0052).

import Link from 'next/link';
import { Suspense, useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from 'next/navigation';

import { Berichtsliste } from '@/components/Berichtsliste';
import { listStockReports, type Page, type ReportSummary } from '@/lib/api';

function HistorieInhalt(): ReactNode {
  const suchparameter = useSearchParams();
  const symbol = suchparameter.get('symbol');
  const [seite, setSeite] = useState<Page<ReportSummary> | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    if (symbol === null) {
      return;
    }
    let abgemeldet = false;
    listStockReports(symbol)
      .then((geladen) => {
        if (!abgemeldet) setSeite(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) {
          setFehler(ursache instanceof Error ? ursache.message : String(ursache));
        }
      });
    return () => {
      abgemeldet = true;
    };
  }, [symbol]);

  if (symbol === null) {
    return <p role="alert">Dieser Aufruf nennt keine Aktie (`?symbol=` fehlt).</p>;
  }
  return (
    <>
      <h1>{symbol}</h1>
      <p>
        <Link href="/">← Tagesübersicht</Link>
      </p>
      {fehler !== null && <p role="alert">Die Historie ist nicht abrufbar: {fehler}.</p>}
      {fehler === null && seite === null && <p>Wird geladen …</p>}
      {seite !== null && (
        <>
          <p className="herkunft">
            {seite.total === 0
              ? 'Diese Aktie war noch in keinem Lauf Kandidat.'
              : `${String(seite.total)} Berichte, neueste zuerst.`}
          </p>
          {seite.items.length > 0 && <Berichtsliste berichte={seite.items} mitDatum />}
        </>
      )}
    </>
  );
}

export default function AktienSeite(): ReactNode {
  return (
    <main>
      <Suspense fallback={<p>Wird geladen …</p>}>
        <HistorieInhalt />
      </Suspense>
    </main>
  );
}
