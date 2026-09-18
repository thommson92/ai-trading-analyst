import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Chartbereich } from '@/components/chart/Chartbereich';
import type { BacktestEpisode, Chartdaten } from '@/lib/api';

// Die Bibliothek zeichnet auf Canvas -- in jsdom gibt es keinen. Hier zaehlt
// nur, dass der Bereich sie richtig anspricht und die Zustaende stimmen.
const setMarkers = vi.fn();
const setData = vi.fn();
vi.mock('lightweight-charts', () => {
  const serie = (): Record<string, unknown> => ({
    setData,
    applyOptions: vi.fn(),
    createPriceLine: vi.fn(),
    attachPrimitive: vi.fn(),
  });
  return {
    CandlestickSeries: 'Candlestick',
    LineSeries: 'Line',
    LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
    CrosshairMode: { Normal: 0 },
    createSeriesMarkers: () => ({ setMarkers }),
    createChart: () => ({
      addSeries: serie,
      applyOptions: vi.fn(),
      panes: () => [{}, { setHeight: vi.fn() }],
      timeScale: () => ({ setVisibleLogicalRange: vi.fn(), timeToCoordinate: () => null }),
      subscribeClick: vi.fn(),
      unsubscribeClick: vi.fn(),
      remove: vi.fn(),
    }),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const KERZEN: Chartdaten = {
  symbol: 'NVDA',
  regelversion: 'g1',
  kerzen: [0, 1, 2, 3, 4, 5].map((i) => ({
    t: new Date(Date.UTC(2026, 0, 5 + i, 14, 30)).toISOString(),
    d: 1,
    o: 100,
    h: 101,
    l: 99,
    c: 100 + i,
    e5: null,
    e20: null,
    rsi: null,
    rma: null,
  })),
  geprueft: 6,
  treffer: 1,
  episoden: 1,
  verworfen: 0,
  warmup: 0,
  kriterien: {},
  gruende: {},
};

const EPISODE: BacktestEpisode = {
  entry_at: KERZEN.kerzen[1]?.t ?? '',
  entry_close: 101,
  signal_types: ['RSI_CROSS', 'EMA5_EMA20_CROSS'],
  letters: 'AC',
  trigger_count: 1,
  last_trigger_at: KERZEN.kerzen[1]?.t ?? '',
  horizons: [
    { horizon: 2, return_pct: 0.02, max_loss: -0.01, drawdown: 0.01, held_above_entry: true },
  ],
};

describe('Der Chartbereich', () => {
  it('sagt, wenn noch keine Episoden vorliegen', () => {
    render(
      <Chartbereich daten={KERZEN} auswertungen={[]} laufzeitpunkt={null} vorgewaehlt={null} />,
    );
    expect(screen.getByText(/noch keine Einzelepisoden/)).toBeTruthy();
    expect(setMarkers).toHaveBeenCalledWith([]);
  });

  it('setzt je Episode einen Marker und oeffnet die vorgewaehlte Episode', () => {
    render(
      <Chartbereich
        daten={KERZEN}
        auswertungen={[
          {
            evaluated_at: '2026-09-18T17:00:00+00:00',
            signal_rule_version: 'g1',
            episodes: [EPISODE],
          },
        ]}
        laufzeitpunkt={KERZEN.kerzen[4]?.t ?? null}
        vorgewaehlt={EPISODE.entry_at}
      />,
    );
    const marker = setMarkers.mock.calls.at(-1)?.[0] as { text: string }[];
    expect(marker.map((m) => m.text)).toEqual(['AC', 'Lauf']);
    expect(screen.getByText(/Signale AC/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'schließen' }));
    expect(screen.getByText('Keine Episode gewählt.')).toBeTruthy();
  });
});
