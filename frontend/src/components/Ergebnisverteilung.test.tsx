import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Ergebnisverteilung, klassiere } from '@/components/Ergebnisverteilung';
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

function summe(werte: readonly number[]): number {
  return klassiere(werte).reduce((zwischen, k) => zwischen + k.verlust + k.gewinn, 0);
}

describe('klassiere', () => {
  // Die Komponente lässt sich in jsdom nicht auf ihre Zählung prüfen:
  // `ResponsiveContainer` hat dort die Breite null und zeichnet keinen
  // einzigen Balken. Geprüft wird deshalb die Funktion selbst.

  it('verliert keinen Wert – auch den größten nicht', () => {
    // Der größte Wert fiele bei naiver Rechnung in eine Klasse, die es nicht
    // gibt, und verschwände lautlos.
    const werte = [-500, -120, -3, 0, 7, 45, 900];

    expect(summe(werte)).toBe(werte.length);
    const klassen = klassiere(werte);
    expect(klassen[klassen.length - 1]?.gewinn).toBe(1);
  });

  it('kommt mit lauter gleichen Werten zurecht', () => {
    // Die Klassenbreite wäre sonst null und jede Zuordnung eine Division
    // durch null.
    const klassen = klassiere([215, 215, 215]);

    expect(klassen.length).toBe(1);
    expect(klassen[0]?.gewinn).toBe(3);
    expect(klassen[0]?.verlust).toBe(0);
  });

  it('zählt die Null als Verlust – wie das Backend', () => {
    // `summarize_variant` zählt `gewinn > 0.0`; eine Null ist dort kein
    // Gewinn. Zwei verschiedene Grenzen ergäben zwei verschiedene Quoten
    // für dieselben Trades.
    const klassen = klassiere([0, 0, 0]);

    expect(klassen[0]?.verlust).toBe(3);
    expect(klassen[0]?.gewinn).toBe(0);
  });

  it('trennt Verlust und Gewinn innerhalb derselben Klasse', () => {
    const klassen = klassiere([-1, 1]);
    const verluste = klassen.reduce((z, k) => z + k.verlust, 0);
    const gewinne = klassen.reduce((z, k) => z + k.gewinn, 0);

    expect(verluste).toBe(1);
    expect(gewinne).toBe(1);
  });

  it('liefert für nichts auch nichts', () => {
    expect(klassiere([])).toEqual([]);
  });
});

describe('Ergebnisverteilung', () => {
  it('sagt es, wenn es keine Trades gibt, statt ein leeres Diagramm zu zeigen', () => {
    const { container } = render(
      <Ergebnisverteilung trades={[]} variante="held" titel="Gehalten" />,
    );

    expect(container.textContent).toContain('keine Trades');
  });

  it('liest die gewählte Variante und nicht die andere', () => {
    // Geprüft wird die Auswahl selbst, nicht die durchgereichte Überschrift:
    // Die gehaltene Variante gewinnt hier, die gemanagte verliert.
    const gemischt = [trade(215, -410), trade(215, -410)];

    expect(summe(gemischt.map((t) => t.held_profit))).toBe(2);
    const { container } = render(
      <Ergebnisverteilung trades={gemischt} variante="managed" titel="Gemanagt" />,
    );

    expect(container.textContent).toContain('Gemanagt');
    expect(container.textContent).not.toContain('keine Trades');
  });
});
