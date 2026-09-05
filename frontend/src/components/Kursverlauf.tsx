'use client';

// Der Kursverlauf mit jedem Urteil der Kandidatenregel -- und den simulierten
// Trades darüber.
//
// Gerechnet wird hier **nichts**: Der Payload kommt fertig aus
// `/stocks/{symbol}/chart` und entsteht dort ausschliesslich mit
// Domain-Funktionen (`build_chart_payload`). Eine zweite Rechnung im Frontend
// zeigte, was diese zweite Rechnung daraus macht, nicht was der Screener
// sieht (Doc 12: keine Geschäftslogik im Frontend).
//
// Linie statt Kerzen: Über fünf Jahre sind das rund 2.500 Kerzen. Als Körper
// gezeichnet wären sie ein Balken breit und nicht lesbar; der Schlusskurs mit
// den beiden EMAs ist die Information, auf der die Regel ohnehin steht.

import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { Chartdaten, SimulierterTrade } from '@/lib/api';
import { AUSGANG_TEXT, formatDatum } from '@/lib/format';

interface Punkt {
  i: number;
  datum: string;
  kurs: number;
  ema5: number | null;
  ema20: number | null;
  rsi: number | null;
  rsiMa: number | null;
  treffer: number | null;
  verworfen: number | null;
  einstieg: number | null;
}

function baueReihe(daten: Chartdaten, einstiege: Set<number>): Punkt[] {
  return daten.kerzen.map((kerze, i) => ({
    i,
    datum: kerze.t,
    kurs: kerze.c,
    ema5: kerze.e5,
    ema20: kerze.e20,
    rsi: kerze.rsi,
    rsiMa: kerze.rma,
    // Getrennte Reihen statt einer Reihe mit Farbe: So steht in der Legende,
    // was ein Punkt bedeutet, und ein verworfener Punkt sieht nie aus wie
    // ein Treffer.
    treffer: kerze.sig !== undefined && kerze.gate === undefined ? kerze.c : null,
    verworfen: kerze.gate !== undefined ? kerze.c : null,
    einstieg: einstiege.has(i) ? kerze.c : null,
  }));
}

// Recharts reicht Achsen- und Tooltip-Werte lose typisiert durch. Statt sie
// zu behaupten, wird hier geprueft: Ein Index, den es nicht gibt, bekommt
// eine leere Beschriftung und keine erfundene.
function Achsenbeschriftung(wert: unknown, reihe: Punkt[]): string {
  if (typeof wert !== 'number') return '';
  const punkt = reihe[wert];
  return punkt === undefined ? '' : formatDatum(punkt.datum);
}

function Zahlbeschriftung(wert: unknown, stellen: number): string {
  return typeof wert === 'number' ? wert.toFixed(stellen) : '–';
}

interface Eigenschaften {
  daten: Chartdaten;
  trades: readonly SimulierterTrade[];
}

export function Kursverlauf({ daten, trades }: Eigenschaften): React.ReactElement {
  const einstiege = new Set(trades.map((trade) => trade.entry_index));
  const reihe = baueReihe(daten, einstiege);
  const tradeJeIndex = new Map(trades.map((trade) => [trade.entry_index, trade]));

  return (
    <div className="chart">
      <p className="chartlegende">
        {daten.geprueft} geprüfte Entscheidungspunkte, {daten.treffer} Treffer in{' '}
        {daten.episoden} Episoden, {daten.verworfen} an einer Torbedingung
        verworfen · Regel {daten.regelversion}
      </p>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={reihe} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="var(--linie)" strokeDasharray="2 4" />
          <XAxis
            dataKey="i"
            tickFormatter={(wert: unknown) => Achsenbeschriftung(wert, reihe)}
            minTickGap={64}
            stroke="var(--gedaempft)"
            fontSize={12}
          />
          <YAxis
            domain={['auto', 'auto']}
            stroke="var(--gedaempft)"
            fontSize={12}
            width={56}
          />
          <Tooltip
            labelFormatter={(wert: unknown) => Achsenbeschriftung(wert, reihe)}
            formatter={(wert: unknown, name: unknown) => [
              Zahlbeschriftung(wert, 2),
              String(name),
            ]}
            contentStyle={{
              background: 'var(--grund)',
              border: '1px solid var(--linie)',
              color: 'var(--schrift)',
            }}
          />
          <Line
            type="monotone"
            dataKey="kurs"
            name="Schlusskurs"
            stroke="var(--schrift)"
            dot={false}
            strokeWidth={1.2}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="ema5"
            name="EMA 5"
            stroke="var(--gedaempft)"
            dot={false}
            strokeWidth={1}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="ema20"
            name="EMA 20"
            stroke="var(--ema20)"
            dot={false}
            strokeWidth={1}
            isAnimationActive={false}
          />
          <Scatter dataKey="verworfen" name="an einer Torbedingung verworfen" fill="var(--gate)" />
          <Scatter dataKey="treffer" name="Entscheidungspunkt" fill="var(--treffer)" />
          <Scatter dataKey="einstieg" name="simulierter Einstieg" fill="var(--einstieg)" />
          {/* Der Strike als Punkt am Einstieg: Eine Linie bis zum Verfall
              braucht den Verfallsindex, und den kennt der Chartpayload
              nicht -- ihn hier zu suchen hiesse rechnen. */}
          {trades.map((trade) => (
            <ReferenceDot
              key={`${String(trade.entry_index)}-${String(trade.strike)}`}
              x={trade.entry_index}
              y={trade.strike}
              r={2}
              fill="var(--einstieg)"
              stroke="none"
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>

      <ResponsiveContainer width="100%" height={120}>
        <ComposedChart data={reihe} margin={{ top: 0, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="var(--linie)" strokeDasharray="2 4" />
          <XAxis dataKey="i" hide />
          <YAxis domain={[0, 100]} ticks={[30, 50, 70]} stroke="var(--gedaempft)" fontSize={12} width={56} />
          <Tooltip
            labelFormatter={(wert: unknown) => Achsenbeschriftung(wert, reihe)}
            contentStyle={{
              background: 'var(--grund)',
              border: '1px solid var(--linie)',
              color: 'var(--schrift)',
            }}
          />
          <Line
            type="monotone"
            dataKey="rsi"
            name="RSI"
            stroke="var(--rsi)"
            dot={false}
            strokeWidth={1.2}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="rsiMa"
            name="RSI-Durchschnitt"
            stroke="var(--gedaempft)"
            dot={false}
            strokeWidth={1}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {tradeJeIndex.size > 0 && (
        <p className="chartlegende">
          {tradeJeIndex.size} simulierte Einstiege. Ausgänge:{' '}
          {[...new Set(trades.map((t) => AUSGANG_TEXT[t.managed_outcome]))].join(', ')}.
        </p>
      )}
    </div>
  );
}
