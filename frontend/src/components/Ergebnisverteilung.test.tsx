import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Ergebnisverteilung } from '@/components/Ergebnisverteilung';
import type { SimulierterTrade } from '@/lib/api';

afterEach(cleanup);

function trade(gehalten: number, gemanagt: number): SimulierterTrade {
  return {
    letters: 'AC',
    entry_index: 100,
    entry_date: '2026-03-06',
    underlying_at_entry: 100,
    strike: 95,
    delta: -0.25,
    volatility: 0.28,
    premium: 2.15,
    capital_at_risk: 9500,
    expiration: '2026-04-17',
    days_to_expiration: 42,
    underlying_at_expiration: 102.5,
    held_outcome: 'EXPIRED_WORTHLESS',
    held_profit: gehalten,
    managed_outcome: 'TAKE_PROFIT',
    managed_profit: gemanagt,
    managed_exit_index: 120,
  };
}

describe('Ergebnisverteilung', () => {
  it('sagt es, wenn es keine Trades gibt, statt ein leeres Diagramm zu zeigen', () => {
    const { container } = render(
      <Ergebnisverteilung trades={[]} variante="held" titel="Gehalten" />,
    );

    expect(container.textContent).toContain('keine Trades');
  });

  it('kommt mit lauter gleichen Werten zurecht', () => {
    // Sonst wäre die Klassenbreite null und jeder Wert fiele in eine Klasse,
    // die es nicht gibt.
    const gleich = [trade(215, 215), trade(215, 215), trade(215, 215)];

    const { container } = render(
      <Ergebnisverteilung trades={gleich} variante="held" titel="Gehalten" />,
    );

    expect(container.textContent).toContain('Gehalten');
    expect(container.textContent).not.toContain('keine Trades');
  });

  it('zeigt die gewählte Variante und nicht die andere', () => {
    const gemischt = [trade(215, -410), trade(215, -410)];

    const { container } = render(
      <Ergebnisverteilung trades={gemischt} variante="managed" titel="Gemanagt" />,
    );

    expect(container.textContent).toContain('Gemanagt');
  });
});
