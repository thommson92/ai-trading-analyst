import { describe, expect, it } from 'vitest';

import type { ReportSummary } from '@/lib/api';
import { formatEmpfehlung, formatScore, sortiereNachSwingScore } from '@/lib/format';

function bericht(symbol: string, swing: number | null): ReportSummary {
  return {
    report_id: symbol,
    symbol,
    created_at: '2026-09-01T16:50:00+00:00',
    recommendation: null,
    swing_score: swing,
    investment_score: null,
  };
}

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

describe('sortiereNachSwingScore', () => {
  it('sortiert absteigend', () => {
    const sortiert = sortiereNachSwingScore([bericht('A', 4.2), bericht('B', 8.1)]);
    expect(sortiert.map((eintrag) => eintrag.symbol)).toEqual(['B', 'A']);
  });

  it('stellt Kandidaten ohne Score ans Ende', () => {
    // INSUFFICIENT_DATA ist der unbekannte Fall, nicht der schlechteste.
    const sortiert = sortiereNachSwingScore([bericht('OHNE', null), bericht('MIT', 1.0)]);
    expect(sortiert.map((eintrag) => eintrag.symbol)).toEqual(['MIT', 'OHNE']);
  });

  it('laesst die Vorlage unveraendert', () => {
    const vorlage = [bericht('A', 1.0), bericht('B', 9.0)];
    sortiereNachSwingScore(vorlage);
    expect(vorlage.map((eintrag) => eintrag.symbol)).toEqual(['A', 'B']);
  });
});
