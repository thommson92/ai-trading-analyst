import { describe, expect, it } from 'vitest';

import type { BacktestEpisode } from '@/lib/api';
import { extreme, gefiltert, kombinationen, quartalVon, quartale, renditen } from '@/lib/episoden';

function episode(entry: string, letters: string, r5: number | null): BacktestEpisode {
  return {
    entry_at: entry,
    entry_close: 100,
    signal_types: [],
    letters,
    trigger_count: 1,
    last_trigger_at: entry,
    horizons: [
      { horizon: 5, return_pct: r5, max_loss: null, drawdown: null, held_above_entry: null },
    ],
  };
}

const EPISODEN = [
  episode('2025-01-10T14:30:00+00:00', 'ABD', 0.02),
  episode('2025-02-10T14:30:00+00:00', 'ABD', -0.01),
  episode('2025-04-10T14:30:00+00:00', 'ACD', 0.05),
  episode('2025-12-30T14:30:00+00:00', 'ACD', null),
];

describe('Filter und Kombinationen', () => {
  it('filtert nach Kombination und Zeitraum', () => {
    expect(gefiltert(EPISODEN, { kombination: 'ABD', von: '', bis: '' })).toHaveLength(2);
    expect(
      gefiltert(EPISODEN, { kombination: '', von: '2025-03-01', bis: '2025-12-31' }),
    ).toHaveLength(2);
    expect(kombinationen(EPISODEN)).toEqual(['ABD', 'ACD']);
  });
});

describe('Quartale', () => {
  it('ordnet Monate den Quartalen zu', () => {
    expect(quartalVon('2025-03-31')).toBe('2025 Q1');
    expect(quartalVon('2025-04-01')).toBe('2025 Q2');
    expect(quartalVon('2025-12-30')).toBe('2025 Q4');
  });

  it('zaehlt nur Episoden, die den Horizont erreicht haben', () => {
    const q = quartale(EPISODEN, 5);
    expect(q).toEqual([
      { quartal: '2025 Q1', anzahl: 2, treffer: 1, quote: 0.5 },
      { quartal: '2025 Q2', anzahl: 1, treffer: 1, quote: 1 },
    ]);
  });
});

describe('Extreme und Renditen', () => {
  it('findet beste und schlechteste und laesst Unerreichtes aus', () => {
    const { beste, schlechteste } = extreme(EPISODEN, 5);
    expect(beste?.letters).toBe('ACD');
    expect(schlechteste?.entry_at).toBe('2025-02-10T14:30:00+00:00');
    expect(renditen(EPISODEN, 5)).toEqual([0.02, -0.01, 0.05]);
  });

  it('hat ohne erreichten Horizont keine Extreme', () => {
    expect(extreme([episode('2025-01-01T14:30:00+00:00', 'A', null)], 5)).toEqual({
      beste: null,
      schlechteste: null,
    });
  });
});
