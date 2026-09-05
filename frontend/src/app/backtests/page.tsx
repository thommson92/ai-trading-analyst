'use client';

// Die Gesamtübersicht: Aktien nebeneinander, über eine Messung.
//
// Zwei Reiter statt einer breiten Tabelle -- der Optionsbacktest vergleicht
// Aktien, der Signal-Backtest vergleicht Signalkombinationen. Sie in eine
// Tabelle zu zwingen hieße, zwei verschiedene Fragen in dieselbe Zeile zu
// schreiben.

import Link from 'next/link';
import { useEffect, useState, type ReactNode } from 'react';

import { Messungskopf } from '@/components/Messungskopf';
import {
  getMessung,
  listMessungen,
  type Aktienzeile,
  type Kombinationsergebnis,
  type Messung,
  type Messungsdetail,
} from '@/lib/api';
import { KONFIDENZ_TEXT, formatGeld, formatProzent, formatZeitpunkt } from '@/lib/format';

type Reiter = 'aktien' | 'kombinationen';

function Aktientabelle({ zeilen }: { zeilen: readonly Aktienzeile[] }): ReactNode {
  if (zeilen.length === 0) {
    return <p className="ohne-grundlage">Diese Messung enthält keinen Trade.</p>;
  }
  return (
    <div className="reiterinhalt">
      <table className="aktienvergleich">
        <thead>
          <tr>
            <th scope="col">Aktie</th>
            <th scope="col">Trades</th>
            <th scope="col">Quote gehalten</th>
            <th scope="col">Quote gemanagt</th>
            <th scope="col">Rendite gehalten</th>
            <th scope="col">Rendite gemanagt</th>
            <th scope="col">Summe gemanagt</th>
            <th scope="col">schlechtester Trade</th>
            <th scope="col">Stichprobe</th>
          </tr>
        </thead>
        <tbody>
          {zeilen.map((zeile) => (
            // Sortiert kommt die Liste aus dem Backend -- nach der Rendite
            // der gemanagten Variante, Aktien ohne belastbare Stichprobe ans
            // Ende. Hier wird nicht umsortiert: Was "gut" heißt, entscheidet
            // nicht die Oberfläche.
            <tr key={zeile.stock_id} className={zeile.managed === null ? 'duenn' : undefined}>
              <th scope="row">
                <Link href={`/aktie?symbol=${encodeURIComponent(zeile.symbol)}`}>
                  {zeile.symbol}
                </Link>
              </th>
              <td className="zahl">{zeile.trades}</td>
              <td className="zahl">{formatProzent(zeile.held?.win_rate ?? null)}</td>
              <td className="zahl">{formatProzent(zeile.managed?.win_rate ?? null)}</td>
              <td className="zahl">
                {formatProzent(zeile.held?.mean_return_on_capital ?? null, 2)}
              </td>
              <td className="zahl">
                {formatProzent(zeile.managed?.mean_return_on_capital ?? null, 2)}
              </td>
              <td className="zahl">{formatGeld(zeile.managed?.total_profit ?? null)}</td>
              {/* Fest in der Tabelle, nicht hinter einem Aufklappen: die Zahl,
                  die eine gute Trefferquote nicht zeigt. */}
              <td className="zahl">{formatGeld(zeile.managed?.worst_profit ?? null)}</td>
              <td>{KONFIDENZ_TEXT[zeile.confidence]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Kombinationstabelle({
  zeilen,
}: {
  zeilen: readonly Kombinationsergebnis[];
}): ReactNode {
  if (zeilen.length === 0) {
    return (
      <p className="ohne-grundlage">
        Keine Signalkombination hat in dieser Messung eine Episode erzeugt.
      </p>
    );
  }
  return (
    <div className="reiterinhalt">
      <table className="aktienvergleich">
        <thead>
          <tr>
            <th scope="col">Kriterien</th>
            <th scope="col">Episoden</th>
            <th scope="col">Trades</th>
            <th scope="col">ohne Trade</th>
            <th scope="col">Quote gehalten</th>
            <th scope="col">Quote gemanagt</th>
            <th scope="col">Rendite gemanagt</th>
            <th scope="col">schlechtester Trade</th>
            <th scope="col">Stichprobe</th>
          </tr>
        </thead>
        <tbody>
          {zeilen.map((zeile) => (
            <tr key={zeile.letters} className={zeile.managed === null ? 'duenn' : undefined}>
              <th scope="row">{zeile.letters}</th>
              <td className="zahl">{zeile.episodes}</td>
              <td className="zahl">{zeile.trades}</td>
              <td className="zahl">{zeile.without_trade}</td>
              <td className="zahl">{formatProzent(zeile.held?.win_rate ?? null)}</td>
              <td className="zahl">{formatProzent(zeile.managed?.win_rate ?? null)}</td>
              <td className="zahl">
                {formatProzent(zeile.managed?.mean_return_on_capital ?? null, 2)}
              </td>
              <td className="zahl">{formatGeld(zeile.managed?.worst_profit ?? null)}</td>
              <td>{KONFIDENZ_TEXT[zeile.confidence]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function BacktestSeite(): ReactNode {
  const [messungen, setMessungen] = useState<Messung[] | null>(null);
  const [gewaehlt, setGewaehlt] = useState<string | null>(null);
  const [detail, setDetail] = useState<Messungsdetail | null>(null);
  const [reiter, setReiter] = useState<Reiter>('aktien');
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    let abgemeldet = false;
    listMessungen()
      .then((geladen) => {
        if (abgemeldet) return;
        setMessungen(geladen);
        // Die jüngste ist die Vorauswahl; ältere bleiben über die Liste
        // erreichbar. Eine Messung überschreibt keine andere.
        setGewaehlt(geladen[0]?.measurement_id ?? null);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) {
          setFehler(ursache instanceof Error ? ursache.message : String(ursache));
        }
      });
    return () => {
      abgemeldet = true;
    };
  }, []);

  useEffect(() => {
    if (gewaehlt === null) return;
    let abgemeldet = false;
    setDetail(null);
    getMessung(gewaehlt)
      .then((geladen) => {
        if (!abgemeldet) setDetail(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) {
          setFehler(ursache instanceof Error ? ursache.message : String(ursache));
        }
      });
    return () => {
      abgemeldet = true;
    };
  }, [gewaehlt]);

  return (
    <main>
      <h1>Backtests</h1>
      <p>
        <Link href="/">← Tagesübersicht</Link>
      </p>
      {fehler !== null && <p role="alert">Nicht abrufbar: {fehler}</p>}
      {messungen !== null && messungen.length === 0 && (
        <p className="ohne-grundlage">
          Es liegt noch keine Messung vor. Der Optionsbacktest ist ein Handlauf:{' '}
          <code>cli options-backtest</code>.
        </p>
      )}
      {messungen !== null && messungen.length > 0 && (
        <p>
          <label htmlFor="messung">Messung: </label>
          <select
            id="messung"
            value={gewaehlt ?? ''}
            onChange={(ereignis) => {
              setGewaehlt(ereignis.target.value);
            }}
          >
            {messungen.map((messung) => (
              <option key={messung.measurement_id} value={messung.measurement_id}>
                {formatZeitpunkt(messung.measured_at)} · Aufschlag{' '}
                {messung.assumptions.volatilitaetsaufschlag ?? '?'} · {messung.stocks}{' '}
                Aktien
              </option>
            ))}
          </select>
        </p>
      )}
      {detail !== null && (
        <>
          <Messungskopf messung={detail.measurement} />
          <div className="reiter" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={reiter === 'aktien'}
              onClick={() => {
                setReiter('aktien');
              }}
            >
              Aktien im Vergleich
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={reiter === 'kombinationen'}
              onClick={() => {
                setReiter('kombinationen');
              }}
            >
              Signalkombinationen
            </button>
          </div>
          {reiter === 'aktien' ? (
            <Aktientabelle zeilen={detail.stocks} />
          ) : (
            <Kombinationstabelle zeilen={detail.overall} />
          )}
        </>
      )}
    </main>
  );
}
