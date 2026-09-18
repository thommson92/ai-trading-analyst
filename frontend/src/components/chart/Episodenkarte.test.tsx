import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Episodenkarte } from '@/components/chart/Episodenkarte';
import type { BacktestEpisode } from '@/lib/api';

afterEach(() => {
  cleanup();
});

const EPISODE: BacktestEpisode = {
  entry_at: '2025-03-06T14:30:00+00:00',
  entry_close: 213.42,
  signal_types: ['RSI_CROSS', 'EMA5_EMA20_CROSS'],
  letters: 'AC',
  trigger_count: 2,
  last_trigger_at: '2025-03-07T14:30:00+00:00',
  horizons: [
    {
      horizon: 5,
      return_pct: 0.0213,
      max_loss: -0.0081,
      drawdown: 0.0112,
      held_above_entry: false,
    },
    { horizon: 20, return_pct: null, max_loss: null, drawdown: null, held_above_entry: null },
  ],
};

describe('Die Episodenkarte', () => {
  it('zeigt Einstieg, Kombination und das Ergebnis je Horizont', () => {
    render(
      <Episodenkarte
        episode={EPISODE}
        horizont={5}
        onHorizont={vi.fn()}
        onVor={null}
        onZurueck={null}
        onSchliessen={vi.fn()}
      />,
    );
    expect(screen.getByText(/213,42 \$/)).toBeTruthy();
    expect(screen.getByText(/Signale AC/)).toBeTruthy();
    expect(screen.getByText('2.13 %')).toBeTruthy();
    // Nicht erreicht ist kein Verlust.
    expect(screen.getByText('nicht erreicht')).toBeTruthy();
  });

  it('schaltet den Horizont um und sperrt Vor/Zurueck ohne Nachbarn', () => {
    const onHorizont = vi.fn();
    render(
      <Episodenkarte
        episode={EPISODE}
        horizont={5}
        onHorizont={onHorizont}
        onVor={null}
        onZurueck={null}
        onSchliessen={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '20 Kerzen' }));
    expect(onHorizont).toHaveBeenCalledWith(20);
    expect(screen.getByRole('button', { name: '← vorige' }).hasAttribute('disabled')).toBe(true);
  });
});
