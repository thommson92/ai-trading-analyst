// Die deutschen Namen der Fundamentalkennzahlen. Eigene Datei, weil sie
// sowohl die Tabelle als auch die Jahresverlaeufe beschriften -- zwei
// Listen liefen bei der naechsten neuen Kennzahl auseinander.
//
// Die Schluessel sind die Namen aus `domain/fundamentals/values.py`
// (`MetricName`). Ein unbekannter Name faellt auf die allgemeine
// Beschriftung zurueck, statt zu verschwinden.

export const KENNZAHL_TEXT: Record<string, string | undefined> = {
  REVENUE: 'Umsatz',
  REVENUE_GROWTH: 'Umsatzwachstum',
  NET_INCOME: 'Nettogewinn',
  NET_INCOME_GROWTH: 'Gewinnwachstum',
  FREE_CASH_FLOW: 'Freier Cashflow',
  GROSS_MARGIN: 'Bruttomarge',
  OPERATING_MARGIN: 'Operative Marge',
  NET_MARGIN: 'Nettomarge',
  FREE_CASH_FLOW_MARGIN: 'Free-Cashflow-Marge',
  RETURN_ON_EQUITY: 'Eigenkapitalrendite',
  RETURN_ON_ASSETS: 'Gesamtkapitalrendite',
  DEBT_TO_EQUITY: 'Verschuldungsgrad',
  CURRENT_RATIO: 'Liquiditätsgrad',
  SHARE_COUNT_GROWTH: 'Aktienzahl (Veränderung)',
  MARKET_CAPITALIZATION: 'Marktkapitalisierung',
  PRICE_EARNINGS_RATIO: 'KGV',
  PRICE_SALES_RATIO: 'KUV',
  PRICE_FREE_CASH_FLOW_RATIO: 'Kurs/Free Cashflow',
};
