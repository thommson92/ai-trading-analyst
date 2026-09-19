// Adressen aus Daten -- die eine Stelle, an der ein `href` nicht mit einem
// konstanten `/` beginnt (ADR 0063, Entscheidung 8).
//
// `public/_headers` erlaubt Inline-Skripte, und damit bewertet `script-src`
// auch `javascript:`-Adressen. Eine Quelle aus einem Bericht darf deshalb nur
// dann klickbar werden, wenn sie nachweislich `https:` ist. Alles andere
// bleibt Text -- auch `http:`, auch `data:`, auch ein Tippfehler.

/** Die Adresse, wenn sie sicher verlinkbar ist -- sonst null. */
export function sichereAdresse(roh: string | null | undefined): string | null {
  if (typeof roh !== 'string') return null;
  let adresse: URL;
  try {
    adresse = new URL(roh);
  } catch {
    return null;
  }
  return adresse.protocol === 'https:' ? adresse.toString() : null;
}
