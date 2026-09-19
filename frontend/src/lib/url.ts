// Adressen im Dashboard. Jeder Pfad beginnt mit einem konstanten `/` --
// darauf besteht sicherheitsheader.test.ts, und die Funktionen hier sind der
// eine Ort, an dem Parameter an eine Adresse kommen.

export function berichtAdresse(reportId: string): string {
  return `/bericht/?id=${encodeURIComponent(reportId)}`;
}

export function aktieAdresse(
  symbol: string,
  optionen: { lauf?: string; episode?: string } = {},
): string {
  const suche = new URLSearchParams({ symbol });
  if (optionen.lauf !== undefined) suche.set('lauf', optionen.lauf);
  if (optionen.episode !== undefined) suche.set('episode', optionen.episode);
  return `/aktie/?${suche.toString()}`;
}

export function laufAdresse(runId: string): string {
  return `/laeufe/?id=${encodeURIComponent(runId)}`;
}
