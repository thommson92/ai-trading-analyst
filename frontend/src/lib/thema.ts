// Die Wahl zwischen dunklem und hellem Design (ADR 0063).
//
// Dunkel ist der Standard; hell ist eine Entscheidung des Lesers und liegt
// als `data-thema` am Wurzelelement, damit `styles/tokens.css` sie sieht.
// Gemerkt wird sie im `localStorage` dieses Browsers -- eine Bequemlichkeit,
// kein Zustand, an dem etwas haengt: Fehlt der Speicher, gilt der Standard.
//
// Was hier bewusst fehlt: ein Inline-Skript, das die Wahl vor dem ersten
// Bild anwendet. Im App-Router ginge das nur als rohes HTML -- und genau das
// verbietet `sicherheitsheader.test.ts`, weil die Richtlinie in
// `public/_headers` auf dieser Zusage steht; `next/script` liefe erst nach
// dem ersten Bild. Wer hell gewaehlt hat, sieht beim Laden deshalb kurz
// dunkel. Das ist der Preis, und er ist bekannt.

export type Thema = 'dunkel' | 'hell';

export const STANDARDTHEMA: Thema = 'dunkel';

const SCHLUESSEL = 'ata-thema';

function istThema(wert: unknown): wert is Thema {
  return wert === 'dunkel' || wert === 'hell';
}

/** Die gemerkte Wahl -- oder der Standard, wenn es keine gibt. */
export function liesThema(): Thema {
  try {
    const gemerkt: unknown = window.localStorage.getItem(SCHLUESSEL);
    return istThema(gemerkt) ? gemerkt : STANDARDTHEMA;
  } catch {
    return STANDARDTHEMA;
  }
}

/** Merkt sich die Wahl, wenn der Browser das zulaesst. */
export function speichereThema(thema: Thema): void {
  try {
    window.localStorage.setItem(SCHLUESSEL, thema);
  } catch {
    // Ein privates Fenster ist keine Fehlkonfiguration: Die Wahl gilt fuer
    // diesen Tab, mehr nicht.
  }
}

/** Setzt das Attribut, auf das die Tokens hoeren. Der Standard traegt keins. */
export function wendeThemaAn(thema: Thema): void {
  const wurzel = document.documentElement;
  if (thema === STANDARDTHEMA) {
    delete wurzel.dataset['thema'];
  } else {
    wurzel.dataset['thema'] = thema;
  }
}

export function anderesThema(thema: Thema): Thema {
  return thema === 'dunkel' ? 'hell' : 'dunkel';
}
