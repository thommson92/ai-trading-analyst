// Die Buchstaben der Signaltypen -- dieselbe Zuordnung wie SIGNAL_BUCHSTABEN
// im Backend. Eine Beschriftung, keine Regel.

export const SIGNALBUCHSTABE: Record<string, string | undefined> = {
  RSI_CROSS: 'A',
  PRICE_EMA20_BREAKOUT: 'B',
  EMA5_EMA20_CROSS: 'C',
  RSI_OVERSOLD: 'D',
  NO_RECENT_EMA_DOWNCROSS: 'E',
};

export const SIGNALTEXT: Record<string, string | undefined> = {
  RSI_CROSS: 'RSI kreuzt seinen Durchschnitt',
  PRICE_EMA20_BREAKOUT: 'Ausbruch über EMA 20',
  EMA5_EMA20_CROSS: 'EMA 5 kreuzt EMA 20',
  RSI_OVERSOLD: 'RSI unter 30',
  NO_RECENT_EMA_DOWNCROSS: 'kein Abwärtskreuz der EMAs',
};

/** Buchstaben in fester Reihenfolge A–E; unbekannte Typen bleiben unsichtbar. */
export function buchstabenVon(typen: readonly string[]): string {
  return ['A', 'B', 'C', 'D', 'E']
    .filter((buchstabe) => typen.some((typ) => SIGNALBUCHSTABE[typ] === buchstabe))
    .join('');
}
