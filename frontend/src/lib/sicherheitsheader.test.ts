// Die Sicherheits-Header und die Annahme, auf der sie stehen.
//
// `public/_headers` erlaubt `'unsafe-inline'` fuer Skripte. Diese
// Zugestaendnis-Entscheidung (2026-09-17) traegt nur unter einer Bedingung:
// dass eingeschleuster Text im Frontend gar keinen Weg zur Ausfuehrung hat,
// weil React alles maskiert und nirgends roher HTML-Code eingesetzt wird.
//
// Die Bedingung ist heute erfuellt. Sie koennte es morgen nicht mehr sein --
// ein einziges `dangerouslySetInnerHTML` genuegt, und niemand daechte dabei
// an eine Datei mit Headern. Deshalb prueft der zweite Test sie.

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const HEADERS = readFileSync(join(process.cwd(), 'public/_headers'), 'utf-8');

function csp(): string {
  const zeile = HEADERS.split('\n').find((z) =>
    z.trim().startsWith('Content-Security-Policy:'),
  );
  if (zeile === undefined) {
    throw new Error('Keine Content-Security-Policy in public/_headers.');
  }
  return zeile.split(':').slice(1).join(':').trim();
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

describe('Die Sicherheits-Header', () => {
  it('verbietet fremde Herkuenfte als Voreinstellung', () => {
    expect(csp()).toContain("default-src 'none'");
  });

  it('laesst kein eval zu', () => {
    // Das ist der Teil, den 'unsafe-inline' ausdruecklich **nicht**
    // mitbringt -- und der wirksame Rest der Richtlinie.
    expect(csp()).not.toContain('unsafe-eval');
  });

  it('erlaubt Skripte und Verbindungen nur von der eigenen Herkunft', () => {
    expect(csp()).toContain("script-src 'self'");
    expect(csp()).toContain("connect-src 'self'");
    expect(csp()).not.toMatch(/https?:\/\//);
  });

  it('verbietet das Einbetten in fremde Seiten', () => {
    expect(csp()).toContain("frame-ancestors 'none'");
    expect(HEADERS).toContain('X-Frame-Options: DENY');
  });

  it('haelt den Datenbaum aus dem Zwischenspeicher', () => {
    // Auf einem geteilten Geraet bliebe das Chiffrat sonst liegen -- und es
    // steht unter demselben Schluessel wie jeder andere Stand.
    const block = HEADERS.slice(HEADERS.indexOf('/data/*'));
    expect(block).toContain('Cache-Control: no-store');
  });

  it('nennt nosniff und unterdrueckt den Verweis auf die Herkunft', () => {
    expect(HEADERS).toContain('X-Content-Type-Options: nosniff');
    expect(HEADERS).toContain('Referrer-Policy: no-referrer');
  });
});

describe('Die Annahme hinter dem zugelassenen Inline-Skript', () => {
  it('kein Bauteil setzt rohes HTML ein', () => {
    const treffer = quelldateien(join(process.cwd(), 'src'))
      .filter((pfad) => /dangerouslySetInnerHTML|\.innerHTML/.test(readFileSync(pfad, 'utf-8')))
      .map((pfad) => pfad.replace(process.cwd(), ''));

    expect(
      treffer,
      "Hier wird rohes HTML eingesetzt. Damit faellt die Begruendung fuer " +
        "'unsafe-inline' in public/_headers weg: Eingeschleuster Text haette " +
        'dann einen Weg zur Ausfuehrung. Entweder die Stelle anders loesen ' +
        'oder die Richtlinie auf Hashes umstellen.',
    ).toEqual([]);
  });
});
