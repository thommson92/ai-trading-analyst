'use client';

// Chart, Episodenkarte und Steuerung zusammen: Der Zustand (gewaehlte
// Episode, Horizont) lebt hier, der Chart zeichnet ihn.

import { useCallback, useEffect, useState, type ReactNode } from 'react';

import { Karte } from '@/components/ui/Karte';
import { Leer } from '@/components/ui/Zustand';
import type { BacktestEpisode, Chartdaten, Episodenauswertung } from '@/lib/api';
import { formatZeitpunkt } from '@/lib/format';

import { Episodenkarte } from './Episodenkarte';
import { Kerzenchart } from './Kerzenchart';

export function Chartbereich({
  daten,
  auswertungen,
  laufzeitpunkt,
  vorgewaehlt,
}: {
  daten: Chartdaten;
  auswertungen: readonly Episodenauswertung[];
  laufzeitpunkt: string | null;
  /** `entry_at` einer Episode, die beim Laden gewaehlt sein soll (`?episode=`). */
  vorgewaehlt: string | null;
}): ReactNode {
  const [auswertung, setAuswertung] = useState(0);
  const [horizont, setHorizont] = useState(10);
  const [gewaehlt, setGewaehlt] = useState<BacktestEpisode | null>(null);
  const [ausserhalb, setAusserhalb] = useState(0);
  const [laufOhneKerze, setLaufOhneKerze] = useState(false);
  const aktuelle = auswertungen[auswertung];
  const episoden = aktuelle?.episodes ?? [];

  useEffect(() => {
    if (vorgewaehlt === null) return;
    setGewaehlt(episoden.find((e) => e.entry_at === vorgewaehlt) ?? null);
  }, [vorgewaehlt, episoden]);

  const beiAusserhalb = useCallback((anzahl: number, ohneKerze: boolean) => {
    setAusserhalb(anzahl);
    setLaufOhneKerze(ohneKerze);
  }, []);

  const stelle =
    gewaehlt === null ? -1 : episoden.findIndex((e) => e.entry_at === gewaehlt.entry_at);
  const vorige = stelle > 0 ? (episoden[stelle - 1] ?? null) : null;
  const naechste =
    stelle >= 0 && stelle < episoden.length - 1 ? (episoden[stelle + 1] ?? null) : null;

  return (
    <Karte
      titel="Kursverlauf und Episoden"
      kopf={
        auswertungen.length > 1 ? (
          <label className="auswahl">
            Auswertung
            <select
              value={auswertung}
              onChange={(ereignis) => {
                setAuswertung(Number(ereignis.target.value));
                setGewaehlt(null);
              }}
            >
              {auswertungen.map((a, i) => (
                <option key={a.evaluated_at} value={i}>
                  {formatZeitpunkt(a.evaluated_at)} · {a.episodes.length} Episoden
                </option>
              ))}
            </select>
          </label>
        ) : undefined
      }
    >
      <p className="gedaempft">
        {daten.geprueft} geprüfte Entscheidungspunkte, {daten.treffer} Treffer in {daten.episoden}{' '}
        Episoden, {daten.verworfen} an einer Torbedingung verworfen · Regel {daten.regelversion}
        {aktuelle !== undefined && (
          <span> · Episoden der Auswertung vom {formatZeitpunkt(aktuelle.evaluated_at)}</span>
        )}
        {ausserhalb > 0 && (
          <span> · {ausserhalb} Einstiege liegen außerhalb der exportierten Kerzen</span>
        )}
        {laufOhneKerze && (
          <span>
            {' '}
            · Die Entscheidungskerze des Laufs liegt außerhalb der exportierten Kerzen; der Kreis
            fehlt deshalb.
          </span>
        )}
      </p>
      <Kerzenchart
        daten={daten}
        episoden={episoden}
        gewaehlt={gewaehlt}
        horizont={horizont}
        laufzeitpunkt={laufzeitpunkt}
        onWahl={setGewaehlt}
        onAusserhalb={beiAusserhalb}
      />
      <p className="chartlegende gedaempft">
        Pfeile: Episoden-Einstiege, gefärbt nach der Rendite des gewählten Horizonts. Kreis:
        Entscheidungskerze des Laufs. Klick auf einen Pfeil öffnet die Episode. Chart: TradingView
        Lightweight Charts™.
      </p>
      {aktuelle === undefined ? (
        <Leer>
          Für diese Aktie liegen noch keine Einzelepisoden vor — sie entstehen ab dem ersten Lauf
          nach ADR 0061.
        </Leer>
      ) : gewaehlt === null ? (
        <Leer>Keine Episode gewählt.</Leer>
      ) : (
        <Episodenkarte
          episode={gewaehlt}
          horizont={horizont}
          onHorizont={setHorizont}
          onVor={
            naechste === null
              ? null
              : () => {
                  setGewaehlt(naechste);
                }
          }
          onZurueck={
            vorige === null
              ? null
              : () => {
                  setGewaehlt(vorige);
                }
          }
          onSchliessen={() => {
            setGewaehlt(null);
          }}
        />
      )}
    </Karte>
  );
}
