import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Backtestansicht } from '@/components/Backtestansicht';
import type { AktienBacktest, Chartdaten } from '@/lib/api';

const getAktienBacktest = vi.fn();
const getChart = vi.fn();

vi.mock('@/lib/api', () => ({
  getAktienBacktest: (...args: unknown[]) => getAktienBacktest(...args) as unknown,
  getChart: (...args: unknown[]) => getChart(...args) as unknown,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const LEER: AktienBacktest = {
  symbol: 'AAPL',
  signal_backtests: [],
  measurement: null,
  combinations: [],
  pooled: null,
  trades: [],
};

const CHART: Chartdaten = {
  symbol: 'AAPL',
  regelversion: 'g1-pruefvorlage-2026-09-03',
  kerzen: [],
  geprueft: 0,
  treffer: 0,
  episoden: 0,
  verworfen: 0,
  warmup: 30,
  kriterien: {},
  gruende: {},
};

describe('Backtestansicht', () => {
  it('sagt beim Laden, dass geladen wird', () => {
    getAktienBacktest.mockReturnValue(new Promise(() => undefined));
    getChart.mockReturnValue(new Promise(() => undefined));

    render(<Backtestansicht symbol="AAPL" />);

    expect(screen.getByText(/wird geladen/i)).not.toBeNull();
  });

  it('zeigt einen Fehler als Fehler und nicht als leeres Ergebnis', async () => {
    // Eine Oberfläche, die einen Abruffehler als "keine Daten" zeigt,
    // behauptet, es gebe nichts.
    getAktienBacktest.mockRejectedValue(new Error('503'));
    getChart.mockResolvedValue(CHART);

    render(<Backtestansicht symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('503');
    });
  });

  it('trennt den Ausfall des Kursverlaufs vom Rest', async () => {
    // Dass keine Kerzen im Bestand liegen, ist eine Auskunft über die
    // Datenlage -- die Kennzahlen daneben bleiben davon gültig.
    getAktienBacktest.mockResolvedValue(LEER);
    getChart.mockRejectedValue(new Error('404'));

    render(<Backtestansicht symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByText(/Kein Kursverlauf/)).not.toBeNull();
    });
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText('Signal-Backtest')).not.toBeNull();
  });

  it('nennt ohne Messung den Grund statt einer leeren Tabelle', async () => {
    getAktienBacktest.mockResolvedValue(LEER);
    getChart.mockResolvedValue(CHART);

    render(<Backtestansicht symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByText(/keine Messung vor/)).not.toBeNull();
    });
    expect(screen.getByText(/cli options-backtest/)).not.toBeNull();
  });

  it('reicht die gewählte Messung an die API durch', async () => {
    // Sonst zeigte die Aktienseite die jüngste Messung, während man von
    // einer älteren kam -- andere Zahlen, gleiche Aktie.
    getAktienBacktest.mockResolvedValue(LEER);
    getChart.mockResolvedValue(CHART);

    render(<Backtestansicht symbol="AAPL" messungId="abc-123" />);

    await waitFor(() => {
      expect(getAktienBacktest).toHaveBeenCalledWith('AAPL', 'abc-123');
    });
  });
});
