'use client';

// Der Backtest-Explorer (ADR 0063): links der Signal-Backtest ueber alle
// Aktien und je Aktie, rechts der Optionsbacktest -- zwei Fragen, zwei
// Bereiche, nie eine gemeinsame Zahl. Adressiert ueber `?ansicht=` und
// `?symbol=`, damit ein Bereich verlinkbar bleibt.

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState, type ReactNode } from 'react';

import { Aktienexplorer } from '@/components/backtest/Aktienexplorer';
import { Optionsexplorer } from '@/components/backtest/Optionsexplorer';
import { Signalvergleich } from '@/components/backtest/Signalvergleich';
import { Karte } from '@/components/ui/Karte';
import { Reiter, type Reiterdefinition } from '@/components/ui/Reiter';
import { Fehler, Laedt, Leer, alsFehlertext } from '@/components/ui/Zustand';
import { getSignalBacktestUeberblick, type SignalBacktestUeberblick } from '@/lib/api';

const REITER: readonly Reiterdefinition[] = [
  { id: 'signal', titel: 'Signal-Backtest' },
  { id: 'optionen', titel: 'Optionsbacktest' },
];

function Signalbereich({
  symbol,
  onSymbol,
}: {
  symbol: string | null;
  onSymbol: (s: string) => void;
}): ReactNode {
  const [ueberblick, setUeberblick] = useState<SignalBacktestUeberblick | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    let abgemeldet = false;
    getSignalBacktestUeberblick()
      .then((geladen) => {
        if (!abgemeldet) setUeberblick(geladen);
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) setFehler(alsFehlertext(ursache));
      });
    return () => {
      abgemeldet = true;
    };
  }, []);

  if (fehler !== null) return <Fehler>Der Signal-Backtest ist nicht abrufbar: {fehler}</Fehler>;
  if (ueberblick === null) return <Laedt />;
  return (
    <>
      <Karte titel="Alle Aktien">
        {ueberblick.stocks.length === 0 ? (
          <Leer>
            Noch keine Auswertung — der Signal-Backtest entsteht im Tageslauf für jeden Kandidaten.
          </Leer>
        ) : (
          <Signalvergleich ueberblick={ueberblick} />
        )}
      </Karte>
      <Karte
        titel="Eine Aktie im Detail"
        kopf={
          <label className="auswahl">
            Aktie
            <select
              value={symbol ?? ''}
              onChange={(e) => {
                onSymbol(e.target.value);
              }}
            >
              <option value="">wählen …</option>
              {ueberblick.stocks.map((s) => (
                <option key={s.symbol} value={s.symbol}>
                  {s.symbol}
                </option>
              ))}
            </select>
          </label>
        }
      >
        {symbol === null ? (
          <Leer>Eine Aktie wählen, um ihre Episoden zu sehen.</Leer>
        ) : (
          <Aktienexplorer symbol={symbol} />
        )}
      </Karte>
    </>
  );
}

function ExplorerInhalt(): ReactNode {
  const suche = useSearchParams();
  const router = useRouter();
  const ansicht = suche.get('ansicht') === 'optionen' ? 'optionen' : 'signal';
  const symbol = suche.get('symbol');

  function setze(schluessel: string, wert: string | null): void {
    const neu = new URLSearchParams(suche.toString());
    if (wert === null || wert === '') neu.delete(schluessel);
    else neu.set(schluessel, wert);
    router.replace(`?${neu.toString()}`, { scroll: false });
  }

  return (
    <main>
      <h1>Backtests</h1>
      <Reiter
        reiter={REITER}
        aktiv={ansicht}
        onWechsel={(id) => {
          setze('ansicht', id);
        }}
        beschriftung="Backtest-Art"
      >
        {ansicht === 'signal' ? (
          <Signalbereich
            symbol={symbol}
            onSymbol={(s) => {
              setze('symbol', s);
            }}
          />
        ) : (
          <Karte titel="Optionsbacktest über alle Aktien">
            <Optionsexplorer />
          </Karte>
        )}
      </Reiter>
    </main>
  );
}

export default function BacktestSeite(): ReactNode {
  return (
    <Suspense
      fallback={
        <main>
          <Laedt />
        </main>
      }
    >
      <ExplorerInhalt />
    </Suspense>
  );
}
