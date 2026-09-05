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

const REITER: readonly { id: Reiter; text: string }[] = [
  { id: 'aktien', text: 'Aktien im Vergleich' },
  { id: 'kombinationen', text: 'Signalkombinationen' },
];

function Aktientabelle({
  zeilen,
  messungId,
}: {
  zeilen: readonly Aktienzeile[];
  messungId: string;
}): ReactNode {
  if (zeilen.length === 0) {
    return <p className="ohne-grundlage">Diese Messung enthält keinen Trade.</p>;
  }
  return (
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
          // Sortiert kommt die Liste aus dem Backend -- nach der Rendite der
          // gemanagten Variante, Aktien ohne belastbare Stichprobe ans Ende.
          // Hier wird nicht umsortiert: Was "gut" heißt, entscheidet nicht
          // die Oberfläche.
          <tr key={zeile.stock_id} className={zeile.managed === null ? 'duenn' : undefined}>
            <th scope="row">
              {/* Die gewählte Messung wandert mit: Sonst zeigte die
                  Aktienseite die Zahlen der jüngsten, während man von einer
                  älteren kam. */}
              <Link
                href={`/aktie?symbol=${encodeURIComponent(zeile.symbol)}&messung=${encodeURIComponent(messungId)}`}
              >
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
  );
}

export default function BacktestSeite(): ReactNode {
  const [messungen, setMessungen] = useState<Messung[] | null>(null);
  const [gewaehlt, setGewaehlt] = useState<string | null>(null);
  const [detail, setDetail] = useState<Messungsdetail | null>(null);
  const [reiter, setReiter] = useState<Reiter>('aktien');
  const [fehler, setFehler] = useState<string | null>(null);
  const [laedt, setLaedt] = useState(true);

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
      })
      .finally(() => {
        if (!abgemeldet) setLaedt(false);
      });
    return () => {
      abgemeldet = true;
    };
  }, []);

  useEffect(() => {
    if (gewaehlt === null) return;
    let abgemeldet = false;
    setDetail(null);
    // Zurueckgesetzt, nicht stehengelassen: Sonst bliebe die Meldung einer
    // gescheiterten Messung ueber der naechsten stehen, die sauber geladen
    // hat -- und behauptete einen Fehler, den es nicht mehr gibt.
    setFehler(null);
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
      {laedt && <p>Wird geladen …</p>}
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
      {/* Ohne diese Zeile sähe der Wechsel auf eine andere Messung aus wie
          eine Seite ohne Inhalt -- ununterscheidbar von "es liegt noch keine
          Messung vor". */}
      {gewaehlt !== null && detail === null && fehler === null && (
        <p>Messung wird geladen …</p>
      )}
      {detail !== null && (
        <>
          <Messungskopf messung={detail.measurement} />
          {/* Das Reitermuster ganz oder gar nicht: Rollen ohne
              `aria-controls`, ohne Bereich und ohne Pfeiltasten melden einem
              Screenreader "Tab, ausgewählt" und lassen offen, wozu. */}
          <div className="reiter" role="tablist" aria-label="Vergleichsachse">
            {REITER.map((eintrag) => (
              <button
                key={eintrag.id}
                type="button"
                role="tab"
                id={`reiter-${eintrag.id}`}
                aria-controls={`bereich-${eintrag.id}`}
                aria-selected={reiter === eintrag.id}
                tabIndex={reiter === eintrag.id ? 0 : -1}
                onClick={() => {
                  setReiter(eintrag.id);
                }}
                onKeyDown={(ereignis) => {
                  const schritt =
                    ereignis.key === 'ArrowRight' ? 1 : ereignis.key === 'ArrowLeft' ? -1 : 0;
                  if (schritt === 0) return;
                  ereignis.preventDefault();
                  const jetzt = REITER.findIndex((r) => r.id === reiter);
                  const naechster = REITER[(jetzt + schritt + REITER.length) % REITER.length];
                  if (naechster !== undefined) setReiter(naechster.id);
                }}
              >
                {eintrag.text}
              </button>
            ))}
          </div>
          <div
            className="reiterinhalt"
            role="tabpanel"
            id={`bereich-${reiter}`}
            aria-labelledby={`reiter-${reiter}`}
          >
            {reiter === 'aktien' ? (
              <Aktientabelle
                zeilen={detail.stocks}
                messungId={detail.measurement.measurement_id}
              />
            ) : (
              <Kombinationstabelle zeilen={detail.overall} />
            )}
          </div>
        </>
      )}
    </main>
  );
}
