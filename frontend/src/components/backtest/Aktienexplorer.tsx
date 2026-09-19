'use client';

// Die Episoden einer Aktie: Auswertung, Filter, Tabelle, Verteilung,
// Trefferquote je Quartal, Beste und Schlechteste -- alles gezaehlt aus
// exportierten Werten, nichts bewertet.

import Link from 'next/link';
import { useEffect, useState, type ReactNode } from 'react';

import { Karte } from '@/components/ui/Karte';
import { Kennzahl, Kennzahlen } from '@/components/ui/Kennzahl';
import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import { Fehler, Laedt, Leer, alsFehlertext } from '@/components/ui/Zustand';
import { getAktienBacktest, type AktienBacktest, type BacktestEpisode } from '@/lib/api';
import {
  ergebnisFuer,
  extreme,
  gefiltert,
  kombinationen,
  quartale,
  renditen,
  type Episodenfilter,
} from '@/lib/episoden';
import { formatKurs, formatProzent, formatZeitpunkt } from '@/lib/format';
import { aktieAdresse } from '@/lib/url';

import { Renditeverteilung } from './Renditeverteilung';

function spalten(symbol: string, horizont: number): readonly Spalte<BacktestEpisode>[] {
  const w = (e: BacktestEpisode): number | null => ergebnisFuer(e, horizont)?.return_pct ?? null;
  return [
    {
      schluessel: 'einstieg',
      titel: 'Einstieg',
      kopf: true,
      render: (e) => (
        <Link href={aktieAdresse(symbol, { episode: e.entry_at })}>
          {formatZeitpunkt(e.entry_at)}
        </Link>
      ),
      sortWert: (e) => e.entry_at,
    },
    {
      schluessel: 'kurs',
      titel: 'Kurs',
      zahl: true,
      render: (e) => formatKurs(e.entry_close),
      sortWert: (e) => e.entry_close,
    },
    {
      schluessel: 'letters',
      titel: 'Kombination',
      render: (e) => e.letters,
      sortWert: (e) => e.letters,
    },
    {
      schluessel: 'trigger',
      titel: 'Trigger',
      zahl: true,
      render: (e) => e.trigger_count,
      sortWert: (e) => e.trigger_count,
    },
    {
      schluessel: 'rendite',
      titel: `Rendite nach ${String(horizont)}`,
      zahl: true,
      render: (e) => formatProzent(w(e), 2),
      sortWert: w,
    },
    {
      schluessel: 'verlust',
      titel: 'Größter Verlust',
      zahl: true,
      render: (e) => formatProzent(ergebnisFuer(e, horizont)?.max_loss ?? null, 2),
      sortWert: (e) => ergebnisFuer(e, horizont)?.max_loss,
    },
    {
      schluessel: 'drawdown',
      titel: 'Drawdown',
      zahl: true,
      render: (e) => formatProzent(ergebnisFuer(e, horizont)?.drawdown ?? null, 2),
      sortWert: (e) => ergebnisFuer(e, horizont)?.drawdown,
    },
    {
      schluessel: 'gehalten',
      titel: 'Über Einstieg',
      render: (e) => {
        const g = ergebnisFuer(e, horizont)?.held_above_entry ?? null;
        return g === null ? '–' : g ? 'stets' : 'nicht stets';
      },
    },
  ];
}

export function Aktienexplorer({ symbol }: { symbol: string }): ReactNode {
  const [backtest, setBacktest] = useState<AktienBacktest | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [auswertung, setAuswertung] = useState(0);
  const [horizont, setHorizont] = useState(10);
  const [filter, setFilter] = useState<Episodenfilter>({ kombination: '', von: '', bis: '' });

  useEffect(() => {
    let abgemeldet = false;
    setBacktest(null);
    setFehler(null);
    setAuswertung(0);
    getAktienBacktest(symbol)
      .then((geladen) => {
        if (!abgemeldet) setBacktest(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) setFehler(alsFehlertext(ursache));
      });
    return () => {
      abgemeldet = true;
    };
  }, [symbol]);

  if (fehler !== null)
    return (
      <Fehler>
        Der Backtest von {symbol} ist nicht abrufbar: {fehler}
      </Fehler>
    );
  if (backtest === null) return <Laedt was={`Backtest ${symbol} wird geladen …`} />;
  const aktuelle = backtest.episode_evaluations[auswertung];
  if (aktuelle === undefined) {
    return (
      <Leer>
        Für {symbol} liegen noch keine Einzelepisoden vor — sie entstehen ab dem ersten Lauf nach
        ADR 0061.
      </Leer>
    );
  }
  const horizonte = aktuelle.episodes[0]?.horizons.map((h) => h.horizon) ?? [5, 10, 20];
  const sichtbar = gefiltert(aktuelle.episodes, filter);
  const { beste, schlechteste } = extreme(sichtbar, horizont);
  const werte = renditen(sichtbar, horizont);
  const treffer = werte.filter((r) => r > 0).length;

  return (
    <>
      <div className="filterzeile">
        {backtest.episode_evaluations.length > 1 && (
          <label>
            Auswertung
            <select
              value={auswertung}
              onChange={(e) => {
                setAuswertung(Number(e.target.value));
              }}
            >
              {backtest.episode_evaluations.map((a, i) => (
                <option key={a.evaluated_at} value={i}>
                  {formatZeitpunkt(a.evaluated_at)} · {a.episodes.length} Episoden
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Horizont
          <select
            value={horizont}
            onChange={(e) => {
              setHorizont(Number(e.target.value));
            }}
          >
            {horizonte.map((h) => (
              <option key={h} value={h}>
                {h} Kerzen
              </option>
            ))}
          </select>
        </label>
        <label>
          Kombination
          <select
            value={filter.kombination}
            onChange={(e) => {
              setFilter({ ...filter, kombination: e.target.value });
            }}
          >
            <option value="">alle</option>
            {kombinationen(aktuelle.episodes).map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <label>
          von
          <input
            type="date"
            value={filter.von}
            onChange={(e) => {
              setFilter({ ...filter, von: e.target.value });
            }}
          />
        </label>
        <label>
          bis
          <input
            type="date"
            value={filter.bis}
            onChange={(e) => {
              setFilter({ ...filter, bis: e.target.value });
            }}
          />
        </label>
      </div>
      <Kennzahlen>
        <Kennzahl
          label="Episoden"
          wert={sichtbar.length}
          hinweis={`${String(werte.length)} erreichen den Horizont`}
        />
        <Kennzahl
          label="Über null"
          wert={werte.length === 0 ? null : formatProzent(treffer / werte.length)}
          hinweis={`${String(treffer)} von ${String(werte.length)}`}
        />
        <Kennzahl
          label="Beste"
          wert={
            beste === null
              ? null
              : formatProzent(ergebnisFuer(beste, horizont)?.return_pct ?? null, 2)
          }
          hinweis={
            beste === null ? undefined : (
              <Link href={aktieAdresse(symbol, { episode: beste.entry_at })}>
                {formatZeitpunkt(beste.entry_at)}
              </Link>
            )
          }
        />
        <Kennzahl
          label="Schlechteste"
          wert={
            schlechteste === null
              ? null
              : formatProzent(ergebnisFuer(schlechteste, horizont)?.return_pct ?? null, 2)
          }
          hinweis={
            schlechteste === null ? undefined : (
              <Link href={aktieAdresse(symbol, { episode: schlechteste.entry_at })}>
                {formatZeitpunkt(schlechteste.entry_at)}
              </Link>
            )
          }
        />
      </Kennzahlen>
      <div className="zweispaltig">
        <Karte titel="Verteilung der Renditen">
          <Renditeverteilung renditen={werte} titel={`Rendite nach ${String(horizont)} Kerzen`} />
        </Karte>
        <Karte titel="Über null je Quartal">
          {quartale(sichtbar, horizont).length === 0 ? (
            <Leer>Keine Episode hat den Horizont erreicht.</Leer>
          ) : (
            <ul className="quartalsliste">
              {quartale(sichtbar, horizont).map((q) => (
                <li key={q.quartal}>
                  <span className="quartal">{q.quartal}</span>
                  <span className="quartalsbalken" aria-hidden="true">
                    <span style={{ width: `${String((q.quote ?? 0) * 100)}%` }} />
                  </span>
                  <span className="zahl">
                    {formatProzent(q.quote, 0)}{' '}
                    <span className="gedaempft">
                      ({q.treffer}/{q.anzahl})
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Karte>
      </div>
      <Karte titel="Alle Episoden">
        <Tabelle
          spalten={spalten(symbol, horizont)}
          zeilen={sichtbar}
          schluesselVon={(e) => e.entry_at}
          sortierung={{ schluessel: 'einstieg', richtung: 'ab' }}
          beschriftung={`Episoden ${symbol}`}
        />
      </Karte>
    </>
  );
}
