'use client';

// Die Einzelaktie (ADR 0063): Kopf mit dem letzten Stand, Kerzenchart mit
// Episoden, Kandidatenhistorie, Signal-Backtest, Optionsbacktest. Adressiert
// ueber `?symbol=`; `?lauf=` markiert die Entscheidungskerze eines Laufs,
// `?episode=` waehlt einen Einstieg vor.

import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState, type ReactNode } from 'react';

import { Signalbacktest } from '@/components/Signalbacktest';
import { Kandidatenhistorie } from '@/components/aktie/Kandidatenhistorie';
import { Optionsbacktest } from '@/components/aktie/Optionsbacktest';
import { Chartbereich } from '@/components/chart/Chartbereich';
import { Kennzahl, Kennzahlen } from '@/components/ui/Kennzahl';
import { Karte } from '@/components/ui/Karte';
import { Fehler, Laedt, Leer, alsFehlertext } from '@/components/ui/Zustand';
import {
  getAktienBacktest,
  getChart,
  listStockReports,
  type AktienBacktest,
  type Chartdaten,
  type ReportSummary,
} from '@/lib/api';
import { formatKurs, formatZeitpunkt } from '@/lib/format';

interface Stand {
  berichte: ReportSummary[];
  gesamt: number;
  backtest: AktienBacktest;
}

function AktieInhalt(): ReactNode {
  const suche = useSearchParams();
  const symbol = suche.get('symbol');
  const messung = suche.get('messung');
  const lauf = suche.get('lauf');
  const episode = suche.get('episode');
  const [stand, setStand] = useState<Stand | null>(null);
  const [chart, setChart] = useState<Chartdaten | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  // Getrennt vom Rest: Dass keine Kerzen im Bestand liegen, ist eine
  // Auskunft ueber die Datenlage; Historie und Kennzahlen bleiben gueltig.
  const [chartfehler, setChartfehler] = useState<string | null>(null);
  // Eine aeltere Messung (`?messung=`) betrifft nur den Optionsbacktest.
  // Sie wird getrennt geladen: Ausserhalb des Servers liegt je Aktie nur
  // die juengste, und dieser eine Fehler soll Historie, Chart und
  // Signal-Backtest nicht mitreissen.
  const [messungsstand, setMessungsstand] = useState<AktienBacktest | null>(null);
  const [messungsfehler, setMessungsfehler] = useState<string | null>(null);

  useEffect(() => {
    if (symbol === null) return;
    let abgemeldet = false;
    // Sonst staenden beim Wechsel der Aktie (Browser-Zurueck) Kerzen,
    // Historie und Fehler der vorigen unter dem neuen Kopf.
    setStand(null);
    setChart(null);
    setFehler(null);
    setChartfehler(null);
    Promise.all([listStockReports(symbol, { limit: 100 }), getAktienBacktest(symbol)])
      .then(([seite, backtest]) => {
        if (!abgemeldet) setStand({ berichte: seite.items, gesamt: seite.total, backtest });
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) setFehler(alsFehlertext(ursache));
      });
    getChart(symbol)
      .then((geladen) => {
        if (!abgemeldet) setChart(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) setChartfehler(alsFehlertext(ursache));
      });
    return () => {
      abgemeldet = true;
    };
  }, [symbol]);

  useEffect(() => {
    setMessungsstand(null);
    setMessungsfehler(null);
    if (symbol === null || messung === null) return;
    let abgemeldet = false;
    getAktienBacktest(symbol, messung)
      .then((geladen) => {
        if (!abgemeldet) setMessungsstand(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) setMessungsfehler(alsFehlertext(ursache));
      });
    return () => {
      abgemeldet = true;
    };
  }, [symbol, messung]);

  if (symbol === null) {
    return <Fehler>Dieser Aufruf nennt keine Aktie (?symbol= fehlt).</Fehler>;
  }
  const letzter = stand?.berichte[0] ?? null;
  const laufbericht =
    lauf === null ? null : (stand?.berichte.find((b) => b.analysis_run_id === lauf) ?? null);
  const juengsteAuswertung = stand?.backtest.signal_backtests.reduce<string | null>(
    (max, e) => (max === null || e.evaluated_at > max ? e.evaluated_at : max),
    null,
  );

  return (
    <>
      <header className="aktienkopf">
        <div>
          <h1>{symbol}</h1>
          {letzter !== null && (
            <p className="gedaempft">
              {letzter.company_name ?? ''} · zuletzt Kandidat am{' '}
              {formatZeitpunkt(letzter.created_at)}
            </p>
          )}
        </div>
        {letzter !== null && (
          <span className="berichtskopf-kurs" title="Kurs zum Zeitpunkt des letzten Berichts">
            {formatKurs(letzter.close)}
          </span>
        )}
      </header>
      {fehler !== null && <Fehler>Die Aktie ist nicht abrufbar: {fehler}</Fehler>}
      {stand === null && fehler === null && <Laedt />}
      {chartfehler !== null && (
        <Karte titel="Kursverlauf und Episoden">
          <Leer>
            Kein Kursverlauf: {chartfehler}. Die Kennzahlen darunter bleiben davon unberührt.
          </Leer>
        </Karte>
      )}
      {chart !== null && stand !== null && (
        <Chartbereich
          key={symbol}
          daten={chart}
          auswertungen={stand.backtest.episode_evaluations}
          laufzeitpunkt={laufbericht?.decision_candle_at ?? null}
          vorgewaehlt={episode}
        />
      )}
      {stand !== null && (
        <>
          <Karte titel="Kandidatenhistorie">
            {stand.gesamt === 0 ? (
              <Leer>Diese Aktie war noch in keinem Lauf Kandidat.</Leer>
            ) : (
              <>
                <p className="gedaempft">
                  {stand.gesamt} Berichte, neueste zuerst — jeder mit dem Stand seines Laufs.
                </p>
                <Kandidatenhistorie berichte={stand.berichte} />
              </>
            )}
          </Karte>
          <Karte titel="Signal-Backtest">
            <p className="gedaempft">
              Was der <strong>Kurs</strong> nach einem Trigger tat. Gemessen an den gespeicherten
              Kerzen — hier ist nichts modelliert.
            </p>
            <Kennzahlen>
              <Kennzahl label="Auswertungen" wert={stand.backtest.episode_evaluations.length} />
              <Kennzahl
                label="Episoden (jüngste Auswertung)"
                wert={stand.backtest.episode_evaluations[0]?.episodes.length ?? null}
              />
              <Kennzahl
                label="Jüngste Auswertung"
                wert={
                  juengsteAuswertung === null || juengsteAuswertung === undefined
                    ? null
                    : formatZeitpunkt(juengsteAuswertung)
                }
              />
            </Kennzahlen>
            <div className="breit">
              <Signalbacktest ergebnisse={stand.backtest.signal_backtests} />
            </div>
          </Karte>
          {messung === null ? (
            <Optionsbacktest backtest={stand.backtest} />
          ) : messungsfehler !== null ? (
            <Karte titel="Optionsbacktest">
              <Fehler>Die gewählte Messung ist nicht abrufbar: {messungsfehler}</Fehler>
            </Karte>
          ) : messungsstand === null ? (
            <Karte titel="Optionsbacktest">
              <Laedt was="Messung wird geladen …" />
            </Karte>
          ) : (
            <Optionsbacktest backtest={messungsstand} />
          )}
        </>
      )}
    </>
  );
}

export default function AktienSeite(): ReactNode {
  return (
    <main>
      <Suspense fallback={<Laedt />}>
        <AktieInhalt />
      </Suspense>
    </main>
  );
}
