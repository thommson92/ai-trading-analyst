'use client';

// Der Signal-Backtest ueber alle Aktien: eine Zeile je Aktie, Kombination
// und Horizont, gefiltert und sortiert im Browser. Zeilen ohne belastbare
// Stichprobe stehen gedaempft -- sie haben keine Zahl, nicht eine schlechte.

import Link from 'next/link';
import { useMemo, useState, type ReactNode } from 'react';

import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { Konfidenz, SignalBacktestUeberblick } from '@/lib/api';
import { KONFIDENZ_TEXT, formatProzent, formatTag } from '@/lib/format';
import { aktieAdresse } from '@/lib/url';

interface Zeile {
  symbol: string;
  letters: string;
  horizont: number;
  evaluated_at: string;
  roh: number;
  gezaehlt: number;
  hit_rate: number | null;
  mean_return: number | null;
  max_loss: number | null;
  held: number | null;
  confidence: Konfidenz;
}

function zeilen(ueberblick: SignalBacktestUeberblick): Zeile[] {
  return ueberblick.stocks.flatMap((s) =>
    s.combinations.flatMap((k) =>
      k.horizons.map((h) => ({
        symbol: s.symbol,
        letters: k.letters,
        horizont: h.horizon,
        evaluated_at: s.evaluated_at,
        roh: h.raw_event_count,
        gezaehlt: h.deduplicated_event_count,
        hit_rate: h.hit_rate,
        mean_return: h.mean_return,
        max_loss: h.max_loss,
        held: h.held_above_entry_rate,
        confidence: h.confidence,
      })),
    ),
  );
}

const SPALTEN: readonly Spalte<Zeile>[] = [
  {
    schluessel: 'symbol',
    titel: 'Aktie',
    kopf: true,
    render: (z) => <Link href={aktieAdresse(z.symbol)}>{z.symbol}</Link>,
    sortWert: (z) => z.symbol,
  },
  {
    schluessel: 'letters',
    titel: 'Kombination',
    render: (z) => z.letters,
    sortWert: (z) => z.letters,
  },
  {
    schluessel: 'horizont',
    titel: 'Horizont',
    zahl: true,
    render: (z) => z.horizont,
    sortWert: (z) => z.horizont,
  },
  {
    schluessel: 'gezaehlt',
    titel: 'Ereignisse',
    zahl: true,
    render: (z) => `${String(z.gezaehlt)} von ${String(z.roh)}`,
    sortWert: (z) => z.gezaehlt,
  },
  {
    schluessel: 'hit_rate',
    titel: 'Trefferquote',
    zahl: true,
    render: (z) => formatProzent(z.hit_rate),
    sortWert: (z) => z.hit_rate,
  },
  {
    schluessel: 'mean_return',
    titel: 'Rendite im Mittel',
    zahl: true,
    render: (z) => formatProzent(z.mean_return, 2),
    sortWert: (z) => z.mean_return,
  },
  {
    schluessel: 'max_loss',
    titel: 'Größter Verlust',
    zahl: true,
    render: (z) => formatProzent(z.max_loss, 2),
    sortWert: (z) => z.max_loss,
  },
  {
    schluessel: 'held',
    titel: 'Durchgehend gehalten',
    zahl: true,
    render: (z) => formatProzent(z.held),
    sortWert: (z) => z.held,
  },
  { schluessel: 'confidence', titel: 'Stichprobe', render: (z) => KONFIDENZ_TEXT[z.confidence] },
  {
    schluessel: 'stand',
    titel: 'Stand',
    render: (z) => formatTag(z.evaluated_at),
    sortWert: (z) => z.evaluated_at,
  },
];

export function Signalvergleich({
  ueberblick,
}: {
  ueberblick: SignalBacktestUeberblick;
}): ReactNode {
  const alle = useMemo(() => zeilen(ueberblick), [ueberblick]);
  const kombinationen = useMemo(() => [...new Set(alle.map((z) => z.letters))].sort(), [alle]);
  const horizonte = useMemo(
    () => [...new Set(alle.map((z) => z.horizont))].sort((a, b) => a - b),
    [alle],
  );
  const [kombination, setKombination] = useState('');
  const [horizont, setHorizont] = useState<number | null>(horizonte[1] ?? horizonte[0] ?? null);
  const [nurBelastbar, setNurBelastbar] = useState(false);

  const sichtbar = alle.filter(
    (z) =>
      (kombination === '' || z.letters === kombination) &&
      (horizont === null || z.horizont === horizont) &&
      (!nurBelastbar || z.confidence !== 'INSUFFICIENT_DATA'),
  );

  return (
    <>
      <div className="filterzeile">
        <label>
          Kombination
          <select
            value={kombination}
            onChange={(e) => {
              setKombination(e.target.value);
            }}
          >
            <option value="">alle</option>
            {kombinationen.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <label>
          Horizont
          <select
            value={horizont ?? ''}
            onChange={(e) => {
              setHorizont(e.target.value === '' ? null : Number(e.target.value));
            }}
          >
            <option value="">alle</option>
            {horizonte.map((h) => (
              <option key={h} value={h}>
                {h} Kerzen
              </option>
            ))}
          </select>
        </label>
        <label className="schalter">
          <input
            type="checkbox"
            checked={nurBelastbar}
            onChange={(e) => {
              setNurBelastbar(e.target.checked);
            }}
          />
          nur mit Stichprobe
        </label>
        <span className="gedaempft">
          {sichtbar.length} Zeilen · Regel {ueberblick.signal_rule_version}
        </span>
      </div>
      <Tabelle
        spalten={SPALTEN}
        zeilen={sichtbar}
        schluesselVon={(z) => `${z.symbol}:${z.letters}:${String(z.horizont)}`}
        sortierung={{ schluessel: 'hit_rate', richtung: 'ab' }}
        beschriftung="Signal-Backtest aller Aktien"
        zeilenklasse={(z) => (z.confidence === 'INSUFFICIENT_DATA' ? 'duenn' : undefined)}
      />
    </>
  );
}
