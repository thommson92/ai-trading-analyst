import { describe, expect, it } from 'vitest';

import type { BacktestEpisode, Chartkerze } from '@/lib/api';
import {
  episodeZurZeit,
  episodenZuMarkern,
  horizontfenster,
  kerzenZuSerien,
  pfadNachEinstieg,
  zeitSekunden,
} from '@/lib/chartdaten';

function kerze(stelle: number, close: number, rsi: number | null = 50): Chartkerze {
  const t = new Date(Date.UTC(2026, 0, 5, 14, 30) + stelle * 3600 * 1000 * 12).toISOString();
  return {
    t,
    d: 1,
    o: close - 1,
    h: close + 1,
    l: close - 2,
    c: close,
    e5: close,
    e20: null,
    rsi,
    rma: rsi,
  };
}

const KERZEN = [100, 102, 101, 103, 99, 105, 107, 106].map((c, i) =>
  kerze(i, c, i === 0 ? null : 55),
);

function episode(stelle: number): BacktestEpisode {
  const k = KERZEN[stelle];
  if (k === undefined) throw new Error('Kerze fehlt');
  return {
    entry_at: k.t,
    entry_close: k.c,
    signal_types: ['RSI_CROSS', 'EMA5_EMA20_CROSS'],
    letters: 'AC',
    trigger_count: 1,
    last_trigger_at: k.t,
    horizons: [
      { horizon: 2, return_pct: 0.01, max_loss: -0.01, drawdown: 0.01, held_above_entry: false },
      { horizon: 20, return_pct: null, max_loss: null, drawdown: null, held_above_entry: null },
    ],
  };
}

describe('kerzenZuSerien', () => {
  it('bildet Kerzen auf Sekunden ab und laesst fehlende Werte als Luecke', () => {
    const serien = kerzenZuSerien(KERZEN);
    expect(serien.kerzen).toHaveLength(8);
    expect(serien.kerzen[0]?.time).toBe(zeitSekunden(KERZEN[0]?.t ?? ''));
    // EMA 20 fehlt ueberall, RSI nur an der ersten Kerze: Whitespace, keine Null.
    expect(serien.ema20.every((p) => p.value === undefined)).toBe(true);
    expect(serien.rsi[0]?.value).toBeUndefined();
    expect(serien.rsi[1]?.value).toBe(55);
    expect(serien.indexVonZeit.get(zeitSekunden(KERZEN[3]?.t ?? ''))).toBe(3);
  });
});

describe('episodenZuMarkern', () => {
  it('setzt je Episode einen Marker mit dem Ergebnis des Horizonts', () => {
    const { marker, ausserhalb } = episodenZuMarkern([episode(1)], kerzenZuSerien(KERZEN), 2);
    expect(marker).toHaveLength(1);
    expect(marker[0]?.ergebnis?.return_pct).toBe(0.01);
    expect(ausserhalb).toBe(0);
  });

  it('meldet Einstiege ausserhalb der Kerzen, statt sie zu verschlucken', () => {
    const fremd = { ...episode(1), entry_at: '2020-01-01T14:30:00.000Z' };
    const { marker, ausserhalb } = episodenZuMarkern(
      [fremd, episode(2)],
      kerzenZuSerien(KERZEN),
      2,
    );
    expect(marker).toHaveLength(1);
    expect(ausserhalb).toBe(1);
  });

  it('hat kein Ergebnis, wenn der Horizont nicht erreicht wurde', () => {
    const { marker } = episodenZuMarkern([episode(1)], kerzenZuSerien(KERZEN), 20);
    expect(marker[0]?.ergebnis).toBeNull();
  });
});

describe('horizontfenster und pfadNachEinstieg', () => {
  it('endet genau bei Einstieg plus Horizont und kappt am Serienende', () => {
    const serien = kerzenZuSerien(KERZEN);
    const einstieg = serien.kerzen[2]?.time ?? 0;
    const fenster = horizontfenster(serien, einstieg, [2, 20]);
    expect(fenster[0]?.bis).toBe(serien.kerzen[4]?.time);
    expect(fenster[1]?.bis).toBe(serien.kerzen[7]?.time);
    expect(pfadNachEinstieg(serien, einstieg, 2).map((p) => p.value)).toEqual([101, 103, 99]);
  });

  it('liefert nichts fuer einen Einstieg ohne Kerze', () => {
    const serien = kerzenZuSerien(KERZEN);
    expect(horizontfenster(serien, 1, [5])).toEqual([]);
    expect(pfadNachEinstieg(serien, 1, 5)).toEqual([]);
  });
});

describe('episodeZurZeit', () => {
  it('findet die Episode zum Klickzeitpunkt', () => {
    const serien = kerzenZuSerien(KERZEN);
    const { marker } = episodenZuMarkern([episode(3)], serien, 2);
    expect(episodeZurZeit(marker, serien.kerzen[3]?.time ?? 0)?.letters).toBe('AC');
    expect(episodeZurZeit(marker, 42)).toBeNull();
  });
});
