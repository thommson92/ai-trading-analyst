'use client';

// Die Jahresreihen der Fundamentalkennzahlen als Chart (ADR 0067).
//
// Ein Bild je Einheit, weil nur gleiche Einheiten eine gemeinsame Achse
// vertragen. Gezeichnet wird **jede** Kennzahl, die die Reihe hergibt --
// eine Auswahl der Oberflaeche liesse Zahlen verschwinden, die das Backend
// gerechnet hat.
//
// Die Farben kommen als CSS-Variablen in die SVG-Attribute; der Themenwechsel
// wirkt damit ohne Zutun.

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { ReactNode } from 'react';

import { KENNZAHL_TEXT } from '@/components/bericht/abschnitte/kennzahlnamen';
import type { Einheit, Kennzahlenreihe } from '@/lib/jahresreihen';
import { beschrifte, formatBetrag } from '@/lib/format';

const FARBEN = [
  'var(--akzent)',
  'var(--gewinn)',
  'var(--warnung)',
  'var(--info)',
  'var(--verlust)',
  'var(--ema5)',
] as const;

const TITEL: Record<Einheit, string> = {
  CURRENCY: 'Geschäftsgang',
  FRACTION: 'Margen und Renditen',
  RATIO: 'Bilanzverhältnisse',
  SHARES: 'Aktienzahl',
};

/** Die Achsenbeschriftung je Einheit -- dieselbe Schreibweise wie in der Tabelle. */
function achsenwert(wert: number, einheit: Einheit): string {
  if (einheit === 'FRACTION') {
    return `${(wert * 100).toLocaleString('de-DE', { maximumFractionDigits: 0 })} %`;
  }
  if (einheit === 'RATIO') {
    return wert.toLocaleString('de-DE', { maximumFractionDigits: 2 });
  }
  // Nur die Abkuerzung verliert ihren Punkt: "130 Mrd" bleibt einzeilig,
  // "130 Mrd." bricht um. Das Tausendertrennzeichen bleibt, wo es ist.
  return formatBetrag(wert).replace(/ (Mrd|Mio)\./, ' $1');
}

function punktwert(wert: number, einheit: Einheit, waehrung: string | null): string {
  if (einheit === 'FRACTION') {
    return `${(wert * 100).toLocaleString('de-DE', { maximumFractionDigits: 1 })} %`;
  }
  if (einheit === 'RATIO') {
    return wert.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return formatBetrag(wert, waehrung ?? '');
}

/** Reihum, damit auch die sechste Kennzahl eine Farbe hat. */
function farbe(stelle: number): string {
  return FARBEN[stelle % FARBEN.length] ?? 'var(--akzent)';
}

function Reihenchart({ reihe }: { reihe: Kennzahlenreihe }): ReactNode {
  const { einheit, namen, punkte, waehrung } = reihe;
  return (
    <figure className="jahresverlauf">
      <figcaption>
        {TITEL[einheit]}
        {waehrung !== null && <span className="gedaempft"> · in {waehrung}</span>}
      </figcaption>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart
          data={punkte.map((p) => ({ jahr: p.jahr, ...p.werte }))}
          margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
        >
          <CartesianGrid stroke="var(--linie)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="jahr" stroke="var(--gedaempft)" fontSize={12} />
          <YAxis
            stroke="var(--gedaempft)"
            fontSize={12}
            // Breit genug fuer "130 Mrd": Bricht der Wert um, schiebt sich
            // die oberste Beschriftung aus dem Bild.
            width={76}
            tickFormatter={(wert: unknown) =>
              typeof wert === 'number' ? achsenwert(wert, einheit) : ''
            }
          />
          <Tooltip
            formatter={(wert: unknown, name: unknown) => [
              typeof wert === 'number' ? punktwert(wert, einheit, waehrung) : '–',
              KENNZAHL_TEXT[String(name)] ?? beschrifte(String(name)),
            ]}
            labelFormatter={(wert: unknown) => `Geschäftsjahr ${String(wert)}`}
            contentStyle={{
              background: 'var(--grund)',
              border: '1px solid var(--linie)',
              color: 'var(--schrift)',
            }}
          />
          <Legend
            formatter={(name: unknown) => KENNZAHL_TEXT[String(name)] ?? beschrifte(String(name))}
            wrapperStyle={{ fontSize: '0.75rem' }}
          />
          {namen.map((name, stelle) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              name={name}
              stroke={farbe(stelle)}
              strokeWidth={2}
              dot={{ r: 3 }}
              // Ohne Einblendung: Das Bild ist eine Auskunft, keine
              // Vorfuehrung -- und ein Chart, der erst nach einer Sekunde
              // vollstaendig ist, ist in einem Screenshot unvollstaendig.
              isAnimationActive={false}
              // Ein fehlendes Jahr wird nicht ueberbrueckt: Die Luecke ist
              // die Aussage, eine durchgezogene Linie waere eine Erfindung.
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </figure>
  );
}

export function Jahresverlauf({ reihen }: { reihen: readonly Kennzahlenreihe[] }): ReactNode {
  return (
    <div className="jahresverlaeufe">
      {reihen.map((reihe) => (
        <Reihenchart key={reihe.einheit} reihe={reihe} />
      ))}
    </div>
  );
}
