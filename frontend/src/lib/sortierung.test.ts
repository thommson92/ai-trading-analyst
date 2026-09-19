import { describe, expect, it } from 'vitest';

import { sortiert, vergleiche } from '@/lib/sortierung';

describe('vergleiche', () => {
  it('stellt fehlende Werte in beiden Richtungen ans Ende', () => {
    expect(vergleiche(null, 1)).toBeGreaterThan(0);
    expect(vergleiche(null, 1, 'ab')).toBeGreaterThan(0);
    expect(vergleiche(1, undefined, 'ab')).toBeLessThan(0);
    expect(vergleiche(null, null)).toBe(0);
  });

  it('vergleicht Zahlen numerisch und Texte sprachlich', () => {
    expect(vergleiche(10, 9)).toBeGreaterThan(0);
    expect(vergleiche('ä', 'b')).toBeLessThan(0);
    expect(vergleiche(2, 3, 'ab')).toBeGreaterThan(0);
  });
});

describe('sortiert', () => {
  it('ist stabil und laesst das Original unberuehrt', () => {
    const zeilen = [
      { s: 'B', w: 1 },
      { s: 'A', w: null },
      { s: 'C', w: 1 },
      { s: 'D', w: 0 },
    ];
    const ergebnis = sortiert(zeilen, (z) => z.w, 'ab');
    expect(ergebnis.map((z) => z.s)).toEqual(['B', 'C', 'D', 'A']);
    expect(zeilen.map((z) => z.s)).toEqual(['B', 'A', 'C', 'D']);
  });
});
