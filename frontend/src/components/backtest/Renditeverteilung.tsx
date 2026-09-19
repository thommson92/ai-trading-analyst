'use client';

import type { ReactNode } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { klassiere } from '@/components/Ergebnisverteilung';
import { formatProzent } from '@/lib/format';

/** Die Renditen der Episoden in Klassen -- dieselbe Einteilung wie beim Optionsbacktest. */
export function Renditeverteilung({
  renditen,
  titel,
}: {
  renditen: readonly number[];
  titel: string;
}): ReactNode {
  const klassen = klassiere(renditen);
  if (klassen.length === 0) {
    return (
      <p className="zustand zustand-leer">{titel}: keine Episode hat den Horizont erreicht.</p>
    );
  }
  return (
    <figure className="verteilung">
      <figcaption>{titel}</figcaption>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={klassen} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="var(--linie)" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="mitte"
            tickFormatter={(w: unknown) => (typeof w === 'number' ? formatProzent(w, 0) : '')}
            stroke="var(--gedaempft)"
            fontSize={12}
            minTickGap={32}
          />
          <YAxis allowDecimals={false} stroke="var(--gedaempft)" fontSize={12} width={32} />
          <Tooltip
            labelFormatter={(w: unknown) => {
              const klasse = klassen.find((k) => k.mitte === w);
              return klasse === undefined
                ? '–'
                : `${formatProzent(klasse.von, 1)} bis ${formatProzent(klasse.bis, 1)}`;
            }}
            formatter={(w: unknown, name: unknown) => [String(w), String(name)]}
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
