import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Laufdetail } from '@/components/laeufe/Laufdetail';
import type { AnalysisRunDetail } from '@/lib/api';

afterEach(() => {
  cleanup();
});

const LAUF: AnalysisRunDetail = {
  id: 'lauf-a',
  status: 'COMPLETED',
  started_at: '2026-09-17T17:50:00+00:00',
  completed_at: '2026-09-17T18:08:00+00:00',
  number_of_stocks: 186,
  candidates_found: 0,
  error_message: null,
  earnings_excluded: 3,
  earnings_unknown: 1,
  module_errors: 0,
  suppressed: [
    {
      symbol: 'MSFT',
      blocking_run_id: 'lauf-0',
      blocking_evaluated_at: '2026-09-15T17:50:00+00:00',
    },
  ],
  suppression_window_days: 7,
};

describe('Das Laufdetail', () => {
  it('zeigt die Sperrliste als abgeleitet und mit dem sperrenden Lauf', () => {
    render(<Laufdetail lauf={LAUF} kandidaten={[]} />);

    expect(
      screen.getByText(/1 Symbole durch die Wiederholsperre .*Fenster 7 Tage, abgeleitet/),
    ).toBeTruthy();
    expect(screen.getByRole('link', { name: 'zum Lauf' }).getAttribute('href')).toMatch(
      /^\/laeufe\/?\?id=lauf-0$/,
    );
    expect(screen.getByText('Dieser Lauf hat keinen Kandidaten hervorgebracht.')).toBeTruthy();
  });

  it('sagt, wenn die Sperre nicht gerechnet wurde, und zeigt keine Liste', () => {
    render(
      <Laufdetail
        lauf={{ ...LAUF, suppressed: [], suppression_window_days: null }}
        kandidaten={[]}
      />,
    );
    expect(screen.getByText('nicht gerechnet')).toBeTruthy();
    expect(screen.queryByText(/Fenster \d+ Tage/)).toBeNull();
  });

  it('nennt die unbekannten Berichtstermine als Warnung, nicht als Entwarnung', () => {
    render(<Laufdetail lauf={LAUF} kandidaten={[]} />);
    expect(screen.getByText(/kein belegter Nichttermin/)).toBeTruthy();
  });
});
