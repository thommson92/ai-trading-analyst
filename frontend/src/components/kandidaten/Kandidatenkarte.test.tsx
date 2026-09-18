import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Kandidatenkarte } from '@/components/kandidaten/Kandidatenkarte';
import type { ReportSummary } from '@/lib/api';

afterEach(() => {
  cleanup();
});

const VOLL: ReportSummary = {
  report_id: 'b-1',
  analysis_run_id: 'lauf-1',
  symbol: 'NVDA',
  created_at: '2026-09-17T18:05:00+00:00',
  recommendation: 'CANDIDATE',
  swing_score: 7.2,
  investment_score: null,
  company_name: 'NVIDIA CORP',
  close: 176.4,
  decision_candle_at: '2026-09-17T17:30:00+00:00',
  signal_letters: 'ABE',
  false_signal_risk: 'HIGH',
  earnings_status: 'UNKNOWN',
  earnings_next_date: null,
  earnings_candles_until: null,
  options_status: 'COMPLETED',
  options_reason: null,
  put_suggestion: {
    strike: 165,
    expiration: '2026-10-16',
    days_to_expiration: 29,
    premium: 2.85,
    annualized_return: 0.21,
    distance_to_price_pct: -0.065,
    liquidity: 'GOOD',
    earnings_within_term: false,
  },
};

describe('Die Kandidatenkarte', () => {
  it('nennt Earnings und Put zuerst, Empfehlung und Scores in zweiter Reihe', () => {
    render(<Kandidatenkarte bericht={VOLL} />);

    expect(screen.getByText('Termin unbekannt')).toBeTruthy();
    expect(screen.getByText(/Strike 165,00 \$/)).toBeTruthy();
    expect(screen.getByText(/je Aktie/)).toBeTruthy();
    expect(screen.getByText('Kandidat')).toBeTruthy();
    expect(screen.getByText('7.2')).toBeTruthy();
    // Kein Investment-Score: ein Strich, keine Null.
    expect(screen.getAllByText('–').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Signale ABE')).toBeTruthy();
    expect(screen.getByText(/Fehlsignalrisiko hoch/)).toBeTruthy();
  });

  it('sagt ohne Optionsdaten, dass keine da sind -- nicht nichts', () => {
    render(
      <Kandidatenkarte
        bericht={{ ...VOLL, put_suggestion: null, options_status: null, options_reason: null }}
      />,
    );
    expect(screen.getByText('keine Optionsdaten')).toBeTruthy();
  });

  it('nennt den Grund, wenn die Optionsanalyse keinen Vorschlag fand', () => {
    render(
      <Kandidatenkarte
        bericht={{
          ...VOLL,
          put_suggestion: null,
          options_status: 'INSUFFICIENT_DATA',
          options_reason: 'kein Strike im Band',
        }}
      />,
    );
    expect(screen.getByText('kein Strike im Band')).toBeTruthy();
  });

  it('verlinkt Bericht und Aktie mit dem Lauf', () => {
    render(<Kandidatenkarte bericht={VOLL} />);
    expect(screen.getByRole('link', { name: 'Bericht' }).getAttribute('href')).toMatch(
      /^\/bericht\/?\?id=b-1$/,
    );
    expect(screen.getByRole('link', { name: 'Aktie' }).getAttribute('href')).toMatch(
      /^\/aktie\/?\?symbol=NVDA&lauf=lauf-1$/,
    );
  });
});
