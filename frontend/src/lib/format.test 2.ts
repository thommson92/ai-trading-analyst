import { describe, expect, it } from 'vitest';

import { formatEmpfehlung, formatScore } from '@/lib/format';

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
