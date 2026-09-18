// Ein Kandidat auf einen Blick (ADR 0063, Entscheidung 6): zuerst die Naehe
// zum Berichtstermin und der Put-Vorschlag, in zweiter Reihe Empfehlung,
// beide Scores und die Signalbuchstaben. Reine Darstellung: Nichts wird
// hier gerechnet oder eingestuft.

import Link from 'next/link';
import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/Badge';
import type { ReportSummary } from '@/lib/api';
import { FEHLSIGNALRISIKO_TEXT, formatKurs } from '@/lib/format';
import { aktieAdresse, berichtAdresse } from '@/lib/url';

import { EarningsHinweis } from './EarningsHinweis';
import { Empfehlungsbadge } from './Empfehlungsbadge';
import { PutVorschlag } from './PutVorschlag';
import { ScoreAnzeige } from './ScoreAnzeige';
import { Signalbuchstaben } from './Signalbuchstaben';

export function Kandidatenkarte({ bericht }: { bericht: ReportSummary }): ReactNode {
  return (
    <article className="kandidatenkarte">
      <header className="kandidatenkarte-kopf">
        <div>
          <Link href={berichtAdresse(bericht.report_id)} className="kandidatenkarte-symbol">
            {bericht.symbol}
          </Link>
          {bericht.company_name !== null && (
            <span className="kandidatenkarte-name">{bericht.company_name}</span>
          )}
        </div>
        <span className="kandidatenkarte-kurs">{formatKurs(bericht.close)}</span>
      </header>
      <div className="kandidatenkarte-reihe">
        <EarningsHinweis
          status={bericht.earnings_status}
          termin={bericht.earnings_next_date}
          kerzen={bericht.earnings_candles_until}
        />
        <PutVorschlag
          vorschlag={bericht.put_suggestion}
          status={bericht.options_status}
          grund={bericht.options_reason}
        />
      </div>
      <div className="kandidatenkarte-reihe kandidatenkarte-zweite">
        <Empfehlungsbadge stufe={bericht.recommendation} />
        <ScoreAnzeige label="Swing" wert={bericht.swing_score} />
        <ScoreAnzeige label="Investment" wert={bericht.investment_score} />
        <Signalbuchstaben buchstaben={bericht.signal_letters} />
        {bericht.false_signal_risk !== null && (
          <Badge variante={bericht.false_signal_risk === 'HIGH' ? 'warnung' : 'neutral'}>
            Fehlsignalrisiko{' '}
            {FEHLSIGNALRISIKO_TEXT[bericht.false_signal_risk] ?? bericht.false_signal_risk}
          </Badge>
        )}
      </div>
      <footer className="kandidatenkarte-fuss">
        <Link href={berichtAdresse(bericht.report_id)}>Bericht</Link>
        <Link
          href={aktieAdresse(
            bericht.symbol,
            bericht.analysis_run_id === null ? {} : { lauf: bericht.analysis_run_id },
          )}
        >
          Aktie
        </Link>
      </footer>
    </article>
  );
}
