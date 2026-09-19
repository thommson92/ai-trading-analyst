import { describe, expect, it } from 'vitest';

import {
  empfehlungsrang,
  formatBetrag,
  formatDatum,
  formatEmpfehlung,
  formatScore,
} from '@/lib/format';

describe('formatScore', () => {
  it('zeigt einen Strich, wo es keinen Score gibt', () => {
    // Eine Null waere die schlechteste Bewertung statt einer fehlenden.
    expect(formatScore(null)).toBe('–');
  });

  it('zeigt eine Nachkommastelle', () => {
    expect(formatScore(7)).toBe('7.0');
  });
});

describe('formatEmpfehlung', () => {
  it('uebersetzt die Stufe', () => {
    expect(formatEmpfehlung('STRONG_CANDIDATE')).toBe('starker Kandidat');
  });

  it('zeigt einen Strich ohne Stufe', () => {
    expect(formatEmpfehlung(null)).toBe('–');
  });
});

describe('formatDatum bei fehlender oder fremder Eingabe', () => {
  it('zeigt nie "Invalid Date"', () => {
    expect(formatDatum('')).toBe('–');
    expect(formatDatum('kein Datum')).toBe('kein Datum');
  });
});

describe('empfehlungsrang', () => {
  it('ordnet die Stufen wie das Backend, Fehlendes ans Ende', () => {
    expect(empfehlungsrang('STRONG_CANDIDATE')).toBe(0);
    expect(empfehlungsrang('INSUFFICIENT_DATA')).toBe(4);
    expect(empfehlungsrang(null)).toBeNull();
  });
});

describe('formatBetrag', () => {
  it('schreibt Milliarden und Millionen kurz, Kleines voll', () => {
    expect(formatBetrag(62363000000, 'USD')).toBe('62,36 Mrd. USD');
    expect(formatBetrag(4500000)).toBe('4,5 Mio.');
    expect(formatBetrag(12345, 'USD')).toBe('12.345 USD');
    expect(formatBetrag(-1200000000, 'USD')).toBe('-1,2 Mrd. USD');
    expect(formatBetrag(null)).toBe('–');
  });
});
