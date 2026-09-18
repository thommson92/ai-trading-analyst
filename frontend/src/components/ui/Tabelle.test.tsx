import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Tabelle, type Spalte } from '@/components/ui/Tabelle';

afterEach(() => {
  cleanup();
});

interface Zeile {
  symbol: string;
  score: number | null;
}

const SPALTEN: readonly Spalte<Zeile>[] = [
  {
    schluessel: 'symbol',
    titel: 'Symbol',
    render: (z) => z.symbol,
    sortWert: (z) => z.symbol,
    kopf: true,
  },
  {
    schluessel: 'score',
    titel: 'Score',
    render: (z) => z.score ?? '–',
    sortWert: (z) => z.score,
    zahl: true,
  },
  { schluessel: 'fest', titel: 'Fest', render: () => 'x' },
];

const ZEILEN: Zeile[] = [
  { symbol: 'B', score: 5 },
  { symbol: 'A', score: null },
  { symbol: 'C', score: 7 },
];

function reihenfolge(): string[] {
  return screen
    .getAllByRole('row')
    .slice(1)
    .map((zeile) => within(zeile).getAllByRole('rowheader')[0]?.textContent ?? '');
}

describe('Die Tabelle', () => {
  it('behaelt ohne Sortierung die Reihenfolge der Daten', () => {
    render(
      <Tabelle
        spalten={SPALTEN}
        zeilen={ZEILEN}
        schluesselVon={(z) => z.symbol}
        beschriftung="Test"
      />,
    );
    expect(reihenfolge()).toEqual(['B', 'A', 'C']);
  });

  it('sortiert Zahlen zuerst absteigend und stellt Striche ans Ende', () => {
    render(
      <Tabelle
        spalten={SPALTEN}
        zeilen={ZEILEN}
        schluesselVon={(z) => z.symbol}
        beschriftung="Test"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Score/ }));
    expect(reihenfolge()).toEqual(['C', 'B', 'A']);
    expect(screen.getByRole('columnheader', { name: /Score/ }).getAttribute('aria-sort')).toBe(
      'descending',
    );

    fireEvent.click(screen.getByRole('button', { name: /Score/ }));
    expect(reihenfolge()).toEqual(['B', 'C', 'A']);
  });

  it('macht eine Spalte ohne Sortierwert nicht anklickbar', () => {
    render(
      <Tabelle
        spalten={SPALTEN}
        zeilen={ZEILEN}
        schluesselVon={(z) => z.symbol}
        beschriftung="Test"
      />,
    );
    expect(screen.queryByRole('button', { name: /Fest/ })).toBeNull();
  });

  it('traegt an jeder Zelle die Spaltenueberschrift fuer den Kartenmodus', () => {
    render(
      <Tabelle
        spalten={SPALTEN}
        zeilen={ZEILEN}
        schluesselVon={(z) => z.symbol}
        beschriftung="Test"
      />,
    );
    const zelle = screen.getAllByRole('cell')[0];
    expect(zelle?.getAttribute('data-label')).toBe('Score');
  });
});
