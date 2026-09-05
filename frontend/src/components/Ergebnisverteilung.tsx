'use client';

// Die Verteilung der Einzelergebnisse -- die Zahl, die eine Trefferquote
// nicht zeigt.
//
// Achtzig Prozent gewonnene Trades neben einer Summe unter null ist ein
// Befund, den erst der schlechteste Einzeltrade erklärt (ADR 0058, Nachtrag
// zu Festlegung 9). Deshalb steht die Verteilung neben den Kennzahlen und
// nicht hinter einem Aufklappen.
//
// Die Klassenbreite ergibt sich aus der Spannweite der Daten. Das ist
// Darstellung, keine Fachlogik: Es wird nichts eingestuft und nichts
// bewertet, nur gezählt, was da ist.

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { SimulierterTrade } from '@/lib/api';
import { formatGeld } from '@/lib/format';

const KLASSEN = 16;

interface Klasse {
  von: number;
  bis: number;
  mitte: number;
  // Zwei getrennte Reihen statt einer eingefaerbten: Verlust und Gewinn sind
  // verschiedene Aussagen, und so steht das auch im Tooltip.
  verlust: number;
  gewinn: number;
}

function klassiere(werte: readonly number[]): Klasse[] {
  if (werte.length === 0) return [];
  const kleinster = Math.min(...werte);
  const groesster = Math.max(...werte);
  if (kleinster === groesster) {
    const alle = werte.length;
    return [
      {
        von: kleinster,
        bis: groesster,
        mitte: kleinster,
        verlust: kleinster <= 0 ? alle : 0,
        gewinn: kleinster > 0 ? alle : 0,
      },
    ];
  }
  const breite = (groesster - kleinster) / KLASSEN;
  const klassen: Klasse[] = Array.from({ length: KLASSEN }, (_, k) => ({
    von: kleinster + k * breite,
    bis: kleinster + (k + 1) * breite,
    mitte: kleinster + (k + 0.5) * breite,
    verlust: 0,
    gewinn: 0,
  }));
  for (const wert of werte) {
    // Der größte Wert fällt sonst in eine Klasse, die es nicht gibt.
    const k = Math.min(KLASSEN - 1, Math.floor((wert - kleinster) / breite));
    const klasse = klassen[k];
    if (klasse === undefined) continue;
    if (wert > 0) klasse.gewinn += 1;
    else klasse.verlust += 1;
  }
  return klassen;
}

interface Eigenschaften {
  trades: readonly SimulierterTrade[];
  variante: 'held' | 'managed';
  titel: string;
}

export function Ergebnisverteilung({
  trades,
  variante,
  titel,
}: Eigenschaften): React.ReactElement {
  const werte = trades.map((trade) =>
    variante === 'held' ? trade.held_profit : trade.managed_profit,
  );
  const klassen = klassiere(werte);
  if (klassen.length === 0) {
    return <p className="ohne-grundlage">{titel}: keine Trades.</p>;
  }
  return (
    <figure className="verteilung">
      <figcaption>{titel}</figcaption>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={klassen} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="var(--linie)" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="mitte"
            tickFormatter={(wert: unknown) =>
              typeof wert === 'number' ? Math.round(wert).toLocaleString('de-DE') : ''
            }
            stroke="var(--gedaempft)"
            fontSize={12}
            minTickGap={32}
          />
          <YAxis allowDecimals={false} stroke="var(--gedaempft)" fontSize={12} width={32} />
          <Tooltip
            labelFormatter={(wert: unknown) =>
              typeof wert === 'number' ? formatGeld(wert) : '–'
            }
            formatter={(wert: unknown, name: unknown) => [String(wert), String(name)]}
            contentStyle={{
              background: 'var(--grund)',
              border: '1px solid var(--linie)',
              color: 'var(--schrift)',
            }}
          />
          <Bar
            dataKey="verlust"
            name="Verlust"
            stackId="a"
            fill="var(--verlust)"
            isAnimationActive={false}
          />
          <Bar
            dataKey="gewinn"
            name="Gewinn"
            stackId="a"
            fill="var(--gewinn)"
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
