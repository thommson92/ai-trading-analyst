// Der einzige Ort, an dem das Dashboard die API kennt.
//
// Hier steht keine Fachlogik (Doc 12): Die Typen bilden ab, was die
// Endpunkte liefern, und die Funktionen holen es. Gerechnet, bewertet und
// eingestuft wird ausschliesslich im Backend.

const BASIS = process.env.NEXT_PUBLIC_API_BASE ?? '';
// Leer im Betrieb: Dashboard und API kommen aus demselben Prozess und damit
// von derselben Herkunft (ADR 0052). Nur `next dev` braucht die Variable,
// weil dort zwei Ports im Spiel sind.

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

export interface AnalysisRunDetail extends AnalysisRun {
  earnings_excluded: number;
  earnings_unknown: number;
  module_errors: number;
}

export interface ReportSummary {
  report_id: string;
  symbol: string;
  created_at: string;
  recommendation: Recommendation | null;
  swing_score: number | null;
  investment_score: number | null;
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

async function holen<T>(pfad: string): Promise<T> {
  const antwort = await fetch(`${BASIS}${pfad}`);
  if (!antwort.ok) {
    // Ausdruecklich werfen statt einen Ersatzwert zurueckzugeben: Eine
    // Oberflaeche, die einen Fehler als leere Liste zeigt, behauptet, es
    // gebe nichts.
    throw new ApiError(antwort.status, pfad);
  }
  return (await antwort.json()) as T;
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
  return holen<Page<AnalysisRun>>(`/api/v1/analysis-runs${anhang}`);
}

// Was "erfolgreich" heisst, entscheidet nicht die Oberflaeche: Ein Lauf, bei
// dem eine von zweihundert Aktien an einem isolierten Modulfehler haengen
// blieb, ist PARTIALLY_COMPLETED -- abgeschlossen, mit gueltigen Ergebnissen
// (Doc 10, Paragraph 11). Nur COMPLETED zu zaehlen hiesse, nach einem
// einzigen Anbieterfehler dauerhaft "noch keiner" anzuzeigen.
export const ERFOLGREICH: readonly RunStatus[] = ['COMPLETED', 'PARTIALLY_COMPLETED'];

export function getRun(runId: string): Promise<AnalysisRunDetail> {
  return holen<AnalysisRunDetail>(`/api/v1/analysis-runs/${runId}`);
}

export function listRunReports(runId: string): Promise<ReportSummary[]> {
  return holen<ReportSummary[]>(`/api/v1/analysis-runs/${runId}/reports`);
}

export function getReport(reportId: string): Promise<ReportDocument> {
  return holen<ReportDocument>(`/api/v1/reports/${reportId}`);
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

export interface AktienBacktest {
  symbol: string;
  signal_backtests: SignalBacktest[];
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
  return holen<Messung[]>('/api/v1/options-backtests');
}

export function getMessung(messungId: string): Promise<Messungsdetail> {
  return holen<Messungsdetail>(`/api/v1/options-backtests/${messungId}`);
}

export function getAktienBacktest(
  symbol: string,
  messungId?: string,
): Promise<AktienBacktest> {
  const anhang = messungId === undefined ? '' : `?measurement_id=${messungId}`;
  return holen<AktienBacktest>(
    `/api/v1/stocks/${encodeURIComponent(symbol)}/backtest${anhang}`,
  );
}

export function getChart(symbol: string): Promise<Chartdaten> {
  return holen<Chartdaten>(`/api/v1/stocks/${encodeURIComponent(symbol)}/chart`);
}
