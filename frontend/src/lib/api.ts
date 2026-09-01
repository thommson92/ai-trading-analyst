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
  optionen: { limit?: number; offset?: number; status?: RunStatus } = {},
): Promise<Page<AnalysisRun>> {
  const suche = new URLSearchParams();
  if (optionen.limit !== undefined) suche.set('limit', String(optionen.limit));
  if (optionen.offset !== undefined) suche.set('offset', String(optionen.offset));
  if (optionen.status !== undefined) suche.set('status', optionen.status);
  const anhang = suche.size > 0 ? `?${suche.toString()}` : '';
  return holen<Page<AnalysisRun>>(`/api/v1/analysis-runs${anhang}`);
}

export function getRun(runId: string): Promise<AnalysisRunDetail> {
  return holen<AnalysisRunDetail>(`/api/v1/analysis-runs/${runId}`);
}

export function listRunReports(runId: string): Promise<ReportSummary[]> {
  return holen<ReportSummary[]>(`/api/v1/analysis-runs/${runId}/reports`);
}
