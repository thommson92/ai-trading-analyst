'use client';

// Beide Backtests einer Aktie -- getrennt.
//
// Der Signal-Backtest sagt, ob das Signal trägt; der Optionsbacktest, ob sich
// damit Geld verdienen ließe. Zwei Fragen, und sie stehen in zwei Blöcken.
// Eine gemeinsame Zahl gibt es nirgends.

import { useEffect, useState, type ReactNode } from 'react';

import { Ergebnisverteilung } from '@/components/Ergebnisverteilung';
import { Kursverlauf } from '@/components/Kursverlauf';
import { Messungskopf } from '@/components/Messungskopf';
import { Signalbacktest } from '@/components/Signalbacktest';
import { Variantenvergleich } from '@/components/Variantenvergleich';
import {
  getAktienBacktest,
  getChart,
  type AktienBacktest,
  type Chartdaten,
} from '@/lib/api';
import { AUSGANG_TEXT, formatDatum, formatGeld, formatProzent } from '@/lib/format';

function Tradetabelle({ backtest }: { backtest: AktienBacktest }): ReactNode {
  if (backtest.trades.length === 0) return null;
  return (
    <details className="tradeliste">
      <summary>Alle {backtest.trades.length} simulierten Trades</summary>
      <table>
        <thead>
          <tr>
            <th scope="col">Einstieg</th>
            <th scope="col">Kriterien</th>
            <th scope="col">Kurs</th>
            <th scope="col">Strike</th>
            <th scope="col">Prämie</th>
            <th scope="col">Verfall</th>
            <th scope="col">Kurs am Verfall</th>
            <th scope="col">gehalten</th>
            <th scope="col">gemanagt</th>
          </tr>
        </thead>
        <tbody>
          {backtest.trades.map((trade) => (
            <tr key={`${String(trade.entry_index)}-${String(trade.strike)}`}>
              <td>{formatDatum(trade.entry_date)}</td>
              <td>{trade.letters}</td>
              <td className="zahl">{trade.underlying_at_entry.toFixed(2)}</td>
              <td className="zahl">{trade.strike.toFixed(2)}</td>
              <td className="zahl">{trade.premium.toFixed(2)}</td>
              <td>{formatDatum(trade.expiration)}</td>
              <td className="zahl">{trade.underlying_at_expiration.toFixed(2)}</td>
              <td className="zahl">
                {formatGeld(trade.held_profit)}
                <span className="ausgang"> {AUSGANG_TEXT[trade.held_outcome]}</span>
              </td>
              <td className="zahl">
                {formatGeld(trade.managed_profit)}
                <span className="ausgang"> {AUSGANG_TEXT[trade.managed_outcome]}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

export function Backtestansicht({
  symbol,
  messungId,
}: {
  symbol: string;
  messungId?: string | null;
}): ReactNode {
  const [backtest, setBacktest] = useState<AktienBacktest | null>(null);
  const [chart, setChart] = useState<Chartdaten | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  // Ausdrücklich getrennt vom Backtest-Fehler: Dass für diese Aktie keine
  // Kerzen im Bestand liegen, ist eine Auskunft über die Datenlage -- die
  // Kennzahlen daneben bleiben davon gültig.
  const [chartfehler, setChartfehler] = useState<string | null>(null);

  useEffect(() => {
    let abgemeldet = false;
    getAktienBacktest(symbol, messungId ?? undefined)
      .then((geladen) => {
        if (!abgemeldet) setBacktest(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) {
          setFehler(ursache instanceof Error ? ursache.message : String(ursache));
        }
      });
    getChart(symbol)
      .then((geladen) => {
        if (!abgemeldet) setChart(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) {
          setChartfehler(ursache instanceof Error ? ursache.message : String(ursache));
        }
      });
    return () => {
      abgemeldet = true;
    };
  }, [symbol, messungId]);

  if (fehler !== null) {
    return <p role="alert">Backtest nicht abrufbar: {fehler}</p>;
  }
  if (backtest === null) {
    return <p>Backtest wird geladen …</p>;
  }

  return (
    <>
      <h2>Kursverlauf und Entscheidungspunkte</h2>
      {chartfehler !== null && (
        <p className="ohne-grundlage">
          Kein Kursverlauf: {chartfehler}. Die Kennzahlen darunter bleiben
          davon unberührt.
        </p>
      )}
      {chart !== null && <Kursverlauf daten={chart} trades={backtest.trades} />}

      <h2>Signal-Backtest</h2>
      <p className="blockhinweis">
        Was der <strong>Kurs</strong> nach einem Trigger tat. Gemessen an den
        gespeicherten Kerzen – hier ist nichts modelliert.
      </p>
      <div className="breit">
        <Signalbacktest ergebnisse={backtest.signal_backtests} />
      </div>

      <h2>Optionsbacktest</h2>
      {backtest.measurement === null || backtest.pooled === null ? (
        <p className="ohne-grundlage">
          Für diese Aktie liegt keine Messung vor. Der Optionsbacktest ist ein
          Handlauf (<code>cli options-backtest</code>) und entsteht nicht im
          Tageslauf.
        </p>
      ) : (
        <>
          <Messungskopf messung={backtest.measurement} />
          <h3>Über alle Signalkombinationen</h3>
          <Variantenvergleich
            held={backtest.pooled.held}
            managed={backtest.pooled.managed}
            konfidenz={backtest.pooled.confidence}
            trades={backtest.pooled.trades}
          />
          <div className="verteilungen">
            <Ergebnisverteilung
              trades={backtest.trades}
              variante="held"
              titel="Einzelergebnisse: gehalten"
            />
            <Ergebnisverteilung
              trades={backtest.trades}
              variante="managed"
              titel="Einzelergebnisse: gemanagt"
            />
          </div>

          <h3>Je Signalkombination</h3>
          {backtest.combinations.length === 0 ? (
            <p className="ohne-grundlage">
              Keine Episode dieser Aktie fiel in eine qualifizierende
              Kombination.
            </p>
          ) : (
            <div className="breit">
            <table className="kombinationen">
              <thead>
                <tr>
                  <th scope="col">Kriterien</th>
                  <th scope="col">Episoden</th>
                  <th scope="col">Trades</th>
                  <th scope="col">ohne Trade</th>
                  <th scope="col">Quote gehalten</th>
                  <th scope="col">Quote gemanagt</th>
                  <th scope="col">Rendite gemanagt</th>
                </tr>
              </thead>
              <tbody>
                {backtest.combinations.map((kombination) => (
                  <tr key={kombination.letters}>
                    <th scope="row">{kombination.letters}</th>
                    <td className="zahl">{kombination.episodes}</td>
                    <td className="zahl">{kombination.trades}</td>
                    <td className="zahl">{kombination.without_trade}</td>
                    <td className="zahl">
                      {formatProzent(kombination.held?.win_rate ?? null)}
                    </td>
                    <td className="zahl">
                      {formatProzent(kombination.managed?.win_rate ?? null)}
                    </td>
                    <td className="zahl">
                      {formatProzent(
                        kombination.managed?.mean_return_on_capital ?? null,
                        2,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
          <Tradetabelle backtest={backtest} />
        </>
      )}
    </>
  );
}
