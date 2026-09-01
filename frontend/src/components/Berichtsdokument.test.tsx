import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Berichtsdokument } from '@/components/Berichtsdokument';
import type { ReportDocument } from '@/lib/api';

afterEach(cleanup);

function dokument(abschnitte: ReportDocument['abschnitte']): ReportDocument {
  return {
    berichtsschema_version: 'report-v2',
    anwendungsversion: '0.1.0',
    scoring_version: 'swing-1.2+long_term-1.0',
    signalregel_version: 'signal-v1',
    lauf_id: 'lauf',
    aktie_id: 'aktie',
    erstellt_am: '2026-09-01T17:00:00+00:00',
    abschnitte,
  };
}

describe('Berichtsdokument', () => {
  it('zeigt eine Luecke samt Grund an, statt den Abschnitt wegzulassen', () => {
    // Der Dauerbetrieb faehrt die Recherche abgeschaltet (ADR 0051). Punkt 8
    // muss deshalb als gekennzeichnete Luecke erscheinen und nicht fehlen.
    render(
      <Berichtsdokument
        dokument={dokument({
          NACHRICHTEN: {
            nummer: 8,
            verfuegbar: false,
            inhalt: null,
            vorbehalte: [{ art: 'FEHLT', grund: 'provider_disabled' }],
          },
        })}
      />,
    );

    expect(screen.getByText(/Nachrichten/)).not.toBeNull();
    expect(screen.getByText(/nicht verfügbar/)).not.toBeNull();
    expect(screen.getByText(/provider_disabled/)).not.toBeNull();
  });

  it('zeigt auch einen Abschnitt, den es hier noch nicht kennt', () => {
    // Faellt eine Beschriftung, soll der Abschnitt unschoen erscheinen und
    // nicht verschwinden.
    render(
      <Berichtsdokument
        dokument={dokument({
          NEUER_ABSCHNITT: { nummer: 19, verfuegbar: true, inhalt: 'etwas', vorbehalte: [] },
        })}
      />,
    );

    expect(screen.getByText(/NEUER_ABSCHNITT/)).not.toBeNull();
    expect(screen.getByText('etwas')).not.toBeNull();
  });

  it('ordnet die Abschnitte nach ihrer Nummer', () => {
    render(
      <Berichtsdokument
        dokument={dokument({
          EMPFEHLUNG: { nummer: 16, verfuegbar: true, inhalt: null, vorbehalte: [] },
          SYMBOL_UND_UNTERNEHMEN: { nummer: 1, verfuegbar: true, inhalt: null, vorbehalte: [] },
        })}
      />,
    );

    const ueberschriften = screen.getAllByRole('heading', { level: 3 });
    expect(ueberschriften[0]?.textContent).toContain('Symbol und Unternehmen');
    expect(ueberschriften[1]?.textContent).toContain('Empfehlung');
  });

  it('zeigt verschachtelte Werte und fehlende Zahlen als Strich', () => {
    render(
      <Berichtsdokument
        dokument={dokument({
          PUT_STRATEGIEN: {
            nummer: 13,
            verfuegbar: true,
            inhalt: {
              status: 'COMPLETED',
              kurs: 231.4,
              verfallstermin: null,
              vorschlaege: [{ strike: 220, annualisierte_rendite: 0.18 }],
            },
            vorbehalte: [],
          },
        })}
      />,
    );

    expect(screen.getByText('Verfallstermin')).not.toBeNull();
    expect(screen.getByText('–')).not.toBeNull();
    expect(screen.getByText('Annualisierte rendite')).not.toBeNull();
    expect(screen.getByText('0.18')).not.toBeNull();
  });
});
