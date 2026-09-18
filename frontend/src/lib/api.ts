// Der einzige Ort, an dem das Dashboard weiss, woher seine Daten kommen.
//
// Hier steht keine Fachlogik (Doc 12): Die Typen bilden ab, was die
// Endpunkte liefern, und die Funktionen holen es. Gerechnet, bewertet und
// eingestuft wird ausschliesslich im Backend.
//
// **Zwei Herkuenfte, eine Oberflaeche** (ADR 0060). Im eigenen Netz liest
// das Dashboard die lesende API des Servers. Ausserhalb gibt es keine API:
// Dort liegt ein Datenbaum aus Dateien, den der Server nach jedem Lauf
// hinaufgeladen hat. Jede Funktion unten nennt deshalb beide Wege
// nebeneinander -- der zweite steht sichtbar neben dem ersten, statt in
// einer Umschreibung von Pfaden versteckt zu sein, die niemand mehr mit dem
// Endpunkt vergleichen kann.

import { datenmodus, type Datenbaum } from './datenbaum';

const BASIS = process.env.NEXT_PUBLIC_API_BASE ?? '';
// Leer im Betrieb: Dashboard und API kommen aus demselben Prozess und damit
// von derselben Herkunft (ADR 0052). Nur `next dev` braucht die Variable,
// weil dort zwei Ports im Spiel sind.

let offenerBaum: Datenbaum | null = null;

/** Meldet den geoeffneten Datenbaum an -- Aufgabe von `Datenzugang`. */
export function setzeDatenbaum(baum: Datenbaum | null): void {
  offenerBaum = baum;
}

/** Der geoeffnete Datenbaum -- fuer Ansichten, die sein Manifest brauchen. */
export function setzeDatenbaumBeobachter(): Datenbaum {
  return baum();
}

function baum(): Datenbaum {
  if (offenerBaum === null) {
    // Kein stiller Ersatz: Ohne geoeffneten Stand gibt es nichts anzuzeigen,
    // und eine leere Liste behauptete, es gebe nichts.
    throw new Error('Der Stand ist noch nicht geoeffnet.');
  }
  return offenerBaum;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type RunStatus =
  | 'SCHEDULED'
  | 'RUNNING'
  | 'SCREENING'
  | 'COMPLETED'
  | 'PARTIALLY_COMPLETED'
  | 'FAILED';

export type Recommendation =
  | 'STRONG_CANDIDATE'
  | 'CANDIDATE'
  | 'WATCH'
  | 'AVOID_FOR_NOW'
  | 'INSUFFICIENT_DATA';

export interface AnalysisRun {
  id: string;
  status: RunStatus;
  started_at: string;
  completed_at: string | null;
  number_of_stocks: number;
  candidates_found: number;
  error_message: string | null;
}

/** Ein Symbol, das die Wiederholsperre aus dem Lauf genommen hat (ADR 0062). */
export interface GesperrtesSymbol {
  symbol: string;
  blocking_run_id: string;
  blocking_evaluated_at: string;
}

export interface AnalysisRunDetail extends AnalysisRun {
  earnings_excluded: number;
  earnings_unknown: number;
  module_errors: number;
  /** Rekonstruiert, nicht aufgezeichnet (ADR 0062); null bei `suppression_window_days` heisst: nicht gerechnet. */
  suppressed: GesperrtesSymbol[];
  suppression_window_days: number | null;
}

export type EarningsStatus = 'EARNINGS_CLEAR' | 'EARNINGS_EXCLUDED' | 'UNKNOWN';

/** Der beste Put-Vorschlag eines Berichts; die Praemie je Aktie, wie im Bericht. */
export interface PutVorschlag {
  strike: number;
  expiration: string;
  days_to_expiration: number;
  premium: number;
  annualized_return: number | null;
  distance_to_price_pct: number | null;
  liquidity: string | null;
  earnings_within_term: boolean | null;
}

/**
 * Die Kurzfassung eines Berichts. Die ersten Werte sind Spalten, die
 * uebrigen liest das Backend aus dem gespeicherten Dokument (ADR 0062) --
 * jedes davon null, wenn der Bericht dazu nichts sagt.
 */
export interface ReportSummary {
  report_id: string;
  analysis_run_id: string;
  symbol: string;
  created_at: string;
  recommendation: Recommendation | null;
  swing_score: number | null;
  investment_score: number | null;
  company_name: string | null;
  close: number | null;
  decision_candle_at: string | null;
  signal_letters: string | null;
  false_signal_risk: string | null;
  earnings_status: EarningsStatus | null;
  earnings_next_date: string | null;
  earnings_candles_until: number | null;
  options_status: string | null;
  options_reason: string | null;
  put_suggestion: PutVorschlag | null;
}

/** Eine Aktie in der Aktienliste mit ihrem letzten Stand (ADR 0062). */
export interface Aktieneintrag {
  symbol: string;
  exchange: string;
  reports_count: number;
  last_report: ReportSummary | null;
  signal_backtest_evaluated_at: string | null;
  episodes_available: boolean;
}

export type JsonWert =
  | string
  | number
  | boolean
  | null
  | JsonWert[]
  | { [schluessel: string]: JsonWert };

export interface Vorbehalt {
  art: string;
  grund: string;
}

export interface Berichtsabschnitt {
  nummer: number;
  verfuegbar: boolean;
  inhalt: JsonWert;
  vorbehalte: Vorbehalt[];
}

export interface ReportDocument {
  berichtsschema_version: string;
  anwendungsversion: string;
  scoring_version: string | null;
  signalregel_version: string;
  lauf_id: string;
  aktie_id: string;
  erstellt_am: string;
  // Die Schluessel sind die achtzehn Abschnittsnamen. Bewusst als offene
  // Zuordnung: Kaeme ein neuer Abschnitt hinzu, soll ihn die Oberflaeche
  // anzeigen und nicht verschlucken.
  abschnitte: Record<string, Berichtsabschnitt>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly pfad: string,
  ) {
    super(`${pfad} antwortete mit ${String(status)}`);
    this.name = 'ApiError';
  }
}

async function holen<T>(pfad: string, ausDemBaum: (baum: Datenbaum) => Promise<T>): Promise<T> {
  if (datenmodus() !== 'api') {
    return await ausDemBaum(baum());
  }
  const antwort = await fetch(`${BASIS}${pfad}`);
  if (!antwort.ok) {
    // Ausdruecklich werfen statt einen Ersatzwert zurueckzugeben: Eine
    // Oberflaeche, die einen Fehler als leere Liste zeigt, behauptet, es
    // gebe nichts.
    throw new ApiError(antwort.status, pfad);
  }
  return (await antwort.json()) as T;
}

function seite<T>(alle: T[], optionen: { limit?: number; offset?: number }): Page<T> {
  // Dieselben Voreinstellungen wie die API (limit 25, offset 0). Geblaettert
  // wird ausserhalb im Browser: Die Listen sind klein -- ein Lauf je
  // Handelstag --, und eine zweite Seitenlogik im Export waere eine zweite
  // Wahrheit ueber dieselbe Reihenfolge.
  const limit = optionen.limit ?? 25;
  const offset = optionen.offset ?? 0;
  return { items: alle.slice(offset, offset + limit), total: alle.length, limit, offset };
}

export function listRuns(
  optionen: { limit?: number; offset?: number; status?: readonly RunStatus[] } = {},
): Promise<Page<AnalysisRun>> {
  const suche = new URLSearchParams();
  if (optionen.limit !== undefined) suche.set('limit', String(optionen.limit));
  if (optionen.offset !== undefined) suche.set('offset', String(optionen.offset));
  // Mehrfach derselbe Name: So nimmt die API eine Liste von Status entgegen.
  for (const status of optionen.status ?? []) suche.append('status', status);
  const anhang = suche.size > 0 ? `?${suche.toString()}` : '';
  return holen<Page<AnalysisRun>>(`/api/v1/analysis-runs${anhang}`, async (baum) => {
    const alle = await baum.lade<AnalysisRun[]>('data/analysis-runs.json');
    const erlaubt = optionen.status;
    const gefiltert =
      erlaubt === undefined ? alle : alle.filter((lauf) => erlaubt.includes(lauf.status));
    return seite(gefiltert, optionen);
  });
}

// Was "erfolgreich" heisst, entscheidet nicht die Oberflaeche: Ein Lauf, bei
// dem eine von zweihundert Aktien an einem isolierten Modulfehler haengen
// blieb, ist PARTIALLY_COMPLETED -- abgeschlossen, mit gueltigen Ergebnissen
// (Doc 10, Paragraph 11). Nur COMPLETED zu zaehlen hiesse, nach einem
// einzigen Anbieterfehler dauerhaft "noch keiner" anzuzeigen.
export const ERFOLGREICH: readonly RunStatus[] = ['COMPLETED', 'PARTIALLY_COMPLETED'];

export function getRun(runId: string): Promise<AnalysisRunDetail> {
  return holen<AnalysisRunDetail>(`/api/v1/analysis-runs/${runId}`, (baum) =>
    baum.lade<AnalysisRunDetail>(`data/analysis-runs/${runId}.json`),
  );
}

export function listRunReports(runId: string): Promise<ReportSummary[]> {
  return holen<ReportSummary[]>(`/api/v1/analysis-runs/${runId}/reports`, (baum) =>
    baum.lade<ReportSummary[]>(`data/analysis-runs/${runId}/reports.json`),
  );
}

export function listStocks(): Promise<Aktieneintrag[]> {
  return holen<Aktieneintrag[]>('/api/v1/stocks', (baum) =>
    baum.lade<Aktieneintrag[]>('data/stocks.json'),
  );
}

export function getReport(reportId: string): Promise<ReportDocument> {
  return holen<ReportDocument>(`/api/v1/reports/${reportId}`, (baum) =>
    baum.lade<ReportDocument>(`data/reports/${reportId}.json`),
  );
}

export function listStockReports(
  symbol: string,
  optionen: { limit?: number; offset?: number } = {},
): Promise<Page<ReportSummary>> {
  const suche = new URLSearchParams();
  if (optionen.limit !== undefined) suche.set('limit', String(optionen.limit));
  if (optionen.offset !== undefined) suche.set('offset', String(optionen.offset));
  const anhang = suche.size > 0 ? `?${suche.toString()}` : '';
  return holen<Page<ReportSummary>>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/reports${anhang}`,
    async (baum) => {
      const alle = await baum.lade<ReportSummary[]>(
        `data/stocks/${baum.verzeichnis(symbol)}/reports.json`,
      );
      return seite(alle, optionen);
    },
  );
}

// --- Backtests (ADR 0058) ------------------------------------------------
//
// Zwei Backtests, und sie bleiben getrennt: Der Signal-Backtest sagt, ob das
// Signal traegt, der Optionsbacktest, ob sich damit Geld verdienen liesse.
// Eine gemeinsame Zahl gibt es nirgends -- weder hier noch im Backend.

export type Konfidenz = 'INSUFFICIENT_DATA' | 'LOW_SAMPLE' | 'NORMAL';

export type Ausgang =
  | 'EXPIRED_WORTHLESS'
  | 'ASSIGNED'
  | 'TAKE_PROFIT'
  | 'STOPPED_OUT'
  | 'CLOSED_AT_EXPIRATION';

export interface VariantenKennzahlen {
  trades: number;
  win_rate: number | null;
  mean_profit: number | null;
  median_profit: number | null;
  total_profit: number | null;
  worst_profit: number | null;
  mean_return_on_capital: number | null;
  outcomes: Record<string, number>;
}

export interface Messung {
  measurement_id: string;
  measured_at: string;
  signal_rule_version: string;
  stocks: number;
  history_start: string;
  history_end: string;
  assumptions: Record<string, string>;
}

export interface Kombinationsergebnis {
  signal_types: string[];
  letters: string;
  episodes: number;
  trades: number;
  without_trade: number;
  confidence: Konfidenz;
  held: VariantenKennzahlen | null;
  managed: VariantenKennzahlen | null;
}

export interface Aktienzeile {
  stock_id: string;
  symbol: string;
  trades: number;
  confidence: Konfidenz;
  held: VariantenKennzahlen | null;
  managed: VariantenKennzahlen | null;
}

export interface Messungsdetail {
  measurement: Messung;
  overall: Kombinationsergebnis[];
  stocks: Aktienzeile[];
}

export interface SimulierterTrade {
  letters: string;
  entry_index: number;
  entry_date: string;
  underlying_at_entry: number;
  strike: number;
  delta: number;
  volatility: number;
  premium: number;
  capital_at_risk: number;
  expiration: string;
  days_to_expiration: number;
  underlying_at_expiration: number;
  held_outcome: Ausgang;
  held_profit: number;
  managed_outcome: Ausgang;
  managed_profit: number;
  managed_exit_index: number;
}

export interface HorizontKennzahlen {
  horizon: number;
  raw_event_count: number;
  deduplicated_event_count: number;
  hit_rate: number | null;
  mean_return: number | null;
  median_return: number | null;
  max_loss: number | null;
  drawdown: number | null;
  held_above_entry_rate: number | null;
  confidence: Konfidenz;
}

export interface SignalBacktest {
  signal_types: string[];
  letters: string;
  signal_rule_version: string;
  evaluated_at: string;
  history_start: string;
  history_end: string;
  horizons: HorizontKennzahlen[];
}

/** Ein Horizont einer Episode; alles null, wenn die Historie ihn nicht erreicht. */
export interface EpisodenHorizont {
  horizon: number;
  return_pct: number | null;
  max_loss: number | null;
  drawdown: number | null;
  held_above_entry: boolean | null;
}

/** Ein gezaehltes Ereignis des Signal-Backtests (ADR 0061). */
export interface BacktestEpisode {
  entry_at: string;
  entry_close: number;
  signal_types: string[];
  letters: string;
  trigger_count: number;
  last_trigger_at: string;
  horizons: EpisodenHorizont[];
}

/** Die Episoden einer Auswertung; die Liste steht je Auswertung, juengste zuerst. */
export interface Episodenauswertung {
  evaluated_at: string;
  signal_rule_version: string;
  episodes: BacktestEpisode[];
}

export interface AktienBacktest {
  symbol: string;
  signal_backtests: SignalBacktest[];
  episode_evaluations: Episodenauswertung[];
  measurement: Messung | null;
  combinations: Kombinationsergebnis[];
  pooled: Aktienzeile | null;
  trades: SimulierterTrade[];
}

export interface Chartkerze {
  t: string;
  d: number;
  o: number;
  h: number;
  l: number;
  c: number;
  e5: number | null;
  e20: number | null;
  rsi: number | null;
  rma: number | null;
  sig?: string[];
  ep?: number;
  first?: boolean;
  gate?: string;
}

export interface Chartdaten {
  symbol: string;
  regelversion: string;
  kerzen: Chartkerze[];
  geprueft: number;
  treffer: number;
  episoden: number;
  verworfen: number;
  warmup: number;
  kriterien: Record<string, string>;
  gruende: Record<string, string>;
}

export function listMessungen(): Promise<Messung[]> {
  return holen<Messung[]>('/api/v1/options-backtests', (baum) =>
    baum.lade<Messung[]>('data/options-backtests.json'),
  );
}

export function getMessung(messungId: string): Promise<Messungsdetail> {
  return holen<Messungsdetail>(`/api/v1/options-backtests/${messungId}`, (baum) =>
    baum.lade<Messungsdetail>(`data/options-backtests/${messungId}.json`),
  );
}

export function getAktienBacktest(
  symbol: string,
  messungId?: string,
): Promise<AktienBacktest> {
  const anhang = messungId === undefined ? '' : `?measurement_id=${messungId}`;
  return holen<AktienBacktest>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/backtest${anhang}`,
    async (baum) => {
      const backtest = await baum.lade<AktienBacktest>(
        `data/stocks/${baum.verzeichnis(symbol)}/backtest.json`,
      );
      // Der Export enthaelt je Aktie **die juengste** Messung (Spike-Bericht
      // 8.2). Eine aeltere anzufordern und stillschweigend die juengste zu
      // bekommen waere die schlimmere Antwort: Die Zahlen saehen richtig aus
      // und gehoerten zu einer anderen Messung.
      if (messungId !== undefined && backtest.measurement?.measurement_id !== messungId) {
        throw new Error(
          'Ausserhalb des Servers liegt je Aktie nur die juengste Messung. ' +
            'Aeltere Messungen sind im Dashboard im eigenen Netz zu sehen.',
        );
      }
      return backtest;
    },
  );
}

/** Der Signal-Backtest ueber alle Aktien: je Aktie die juengste Auswertung (ADR 0062). */
export interface SignalBacktestUeberblick {
  signal_rule_version: string;
  stocks: { symbol: string; evaluated_at: string; combinations: SignalBacktest[] }[];
}

export function getSignalBacktestUeberblick(): Promise<SignalBacktestUeberblick> {
  return holen<SignalBacktestUeberblick>('/api/v1/signal-backtests', (baum) =>
    baum.lade<SignalBacktestUeberblick>('data/signal-backtests.json'),
  );
}

export function getChart(symbol: string): Promise<Chartdaten> {
  return holen<Chartdaten>(`/api/v1/stocks/${encodeURIComponent(symbol)}/chart`, (baum) =>
    baum.lade<Chartdaten>(`data/stocks/${baum.verzeichnis(symbol)}/chart.json`),
  );
}
