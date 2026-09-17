// Die Sicherheits-Header und die zwei Annahmen, auf denen sie stehen.
//
// `public/_headers` erlaubt `'unsafe-inline'` fuer Skripte. Diese
// Zugestaendnis-Entscheidung (2026-09-17) traegt nur, solange
// eingeschleuster Text im Frontend keinen Weg zur Ausfuehrung hat. Es gibt
// dafuer **zwei** Wege, nicht einen:
//
//   1. Rohes HTML (`dangerouslySetInnerHTML` und Verwandte).
//   2. `javascript:`-URLs in `href`/`src`. Die bewertet `script-src`, und
//      `'unsafe-inline'` erlaubt sie -- das ist die Senke, die das
//      Zugestaendnis ueberhaupt erst oeffnet.
//
// Beide sind heute verschlossen. Sie koennten es morgen nicht mehr sein, und
// niemand daechte dabei an eine Datei mit Headern. Deshalb stehen sie hier.

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const HEADERS = readFileSync(join(process.cwd(), 'public/_headers'), 'utf-8');

/** Die Kopfzeilen eines Pfadblocks -- Kommentare und Einrueckung entfernt. */
function block(muster: string): Map<string, string> {
  const zeilen = HEADERS.split('\n');
  const start = zeilen.findIndex((z) => z.trimEnd() === muster);
  if (start < 0) {
    throw new Error(`Kein Block fuer '${muster}' in public/_headers.`);
  }
  const kopfzeilen = new Map<string, string>();
  for (const zeile of zeilen.slice(start + 1)) {
    if (!/^\s/.test(zeile) || zeile.trim() === '') {
      break; // Der naechste Block beginnt.
    }
    const inhalt = zeile.trim();
    if (inhalt.startsWith('#')) {
      continue;
    }
    const doppelpunkt = inhalt.indexOf(':');
    kopfzeilen.set(inhalt.slice(0, doppelpunkt).trim(), inhalt.slice(doppelpunkt + 1).trim());
  }
  return kopfzeilen;
}

/** Die CSP des `/*`-Blocks, zerlegt in Direktive -> erlaubte Quellen. */
function richtlinie(): Map<string, string[]> {
  const roh = block('/*').get('Content-Security-Policy');
  if (roh === undefined) {
    throw new Error('Der /*-Block traegt keine Content-Security-Policy.');
  }
  return new Map(
    roh.split(';').map((teil) => {
      const [name = '', ...quellen] = teil.trim().split(/\s+/);
      return [name, quellen] as const;
    }),
  );
}

function quelldateien(verzeichnis: string): string[] {
  return readdirSync(verzeichnis).flatMap((eintrag) => {
    const pfad = join(verzeichnis, eintrag);
    if (statSync(pfad).isDirectory()) {
      return quelldateien(pfad);
    }
    return /\.tsx?$/.test(eintrag) && !eintrag.includes('.test.') ? [pfad] : [];
  });
}

describe('Die Richtlinie des /*-Blocks', () => {
  // **Positiv gepruefte Allowlist, keine Blockliste.** Eine Blockliste
  // ("kein https://") laesst `data:` und `*` durch, und beides ist ein
  // Lehrbuch-Bypass.
  const ERLAUBT: Record<string, string[]> = {
    'default-src': ["'none'"],
    'script-src': ["'self'", "'unsafe-inline'"],
    'script-src-attr': ["'none'"],
    'style-src': ["'self'", "'unsafe-inline'"],
    'connect-src': ["'self'"],
    'img-src': ["'self'"],
    'font-src': ["'none'"],
    'worker-src': ["'none'"],
    'base-uri': ["'none'"],
    'form-action': ["'none'"],
    'frame-ancestors': ["'none'"],
  };

  it('nennt jede Direktive, auf die es hier ankommt', () => {
    expect([...richtlinie().keys()].sort()).toEqual(Object.keys(ERLAUBT).sort());
  });

  it('laesst je Direktive nur die vorgesehenen Quellen zu', () => {
    for (const [name, quellen] of richtlinie()) {
      expect(quellen, `Direktive ${name}`).toEqual(ERLAUBT[name]);
    }
  });

  it('nennt die uebrigen Sicherheits-Header', () => {
    const kopf = block('/*');
    expect(kopf.get('X-Content-Type-Options')).toBe('nosniff');
    expect(kopf.get('Referrer-Policy')).toBe('no-referrer');
    expect(kopf.get('X-Frame-Options')).toBe('DENY');
    expect(kopf.get('Cross-Origin-Opener-Policy')).toBe('same-origin');
    expect(kopf.get('Strict-Transport-Security')).toMatch(/max-age=\d{7,}/);
  });
});

describe('Der Datenbaum', () => {
  it('gehoert in keinen Zwischenspeicher', () => {
    expect(block('/data/*').get('Cache-Control')).toBe('no-store');
  });
});

describe('Die Annahmen hinter dem zugelassenen Inline-Skript', () => {
  const DATEIEN = quelldateien(join(process.cwd(), 'src'));

  it('kein Bauteil setzt rohes HTML ein', () => {
    const muster =
      /dangerouslySetInnerHTML|innerHTML|outerHTML|insertAdjacentHTML|document\.write|srcDoc|\beval\(|new Function\(/;
    const treffer = DATEIEN.filter((pfad) => muster.test(readFileSync(pfad, 'utf-8'))).map((p) =>
      p.replace(process.cwd(), ''),
    );

    expect(
      treffer,
      'Hier wird roher HTML- oder Skriptinhalt eingesetzt. Damit faellt die ' +
        "erste Begruendung fuer 'unsafe-inline' in public/_headers weg.",
    ).toEqual([]);
  });

  it('jedes href und src beginnt mit einem konstanten Pfad', () => {
    // Die Senke, die 'unsafe-inline' tatsaechlich oeffnet: Ein `href`, das
    // aus Daten stammt, koennte `javascript:` tragen. Ein konstantes
    // Praefix schliesst das aus -- eine Zeichenkette oder ein Template, das
    // mit '/' beginnt.
    const treffer: string[] = [];
    for (const pfad of DATEIEN) {
      for (const fund of readFileSync(pfad, 'utf-8').matchAll(/\b(?:href|src)=(.{0,3})/g)) {
        const anfang = fund[1] ?? '';
        if (!/^(["'`]\/|\{`\/)/.test(anfang)) {
          treffer.push(`${pfad.replace(process.cwd(), '')}: ${anfang}`);
        }
      }
    }

    expect(
      treffer,
      'Hier beginnt ein href oder src nicht mit einem konstanten Pfad. Kaeme ' +
        "der Wert aus Daten, liesse 'unsafe-inline' eine javascript:-URL zu. " +
        'Entweder das Schema pruefen oder die Richtlinie auf Hashes umstellen.',
    ).toEqual([]);
  });
});

describe('Der Weg in den Export', () => {
  it('nimmt die Datei mit, wenn gebaut wurde', () => {
    // Die stillste Bruchstelle: ein geaenderter distDir, ein anderer
    // Kopierschritt -- und die Header fehlen draussen, ohne dass etwas rot
    // wird. Ohne Build laesst sich das hier nicht pruefen.
    const ausgabe = join(process.cwd(), 'out');
    if (!existsSync(ausgabe)) {
      return;
    }
    expect(existsSync(join(ausgabe, '_headers'))).toBe(true);
  });
});
