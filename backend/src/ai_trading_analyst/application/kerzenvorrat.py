"""Die Kerzenserien, die der Lauf schon gerechnet hat.

Der Export zeichnet fuer jede Aktie einen Chart und leitet dafuer dieselbe
Kerzenserie ab, die die Analyse eine halbe Stunde vorher schon abgeleitet
hat -- aus denselben Bars, mit denselben Parametern, zum selben Ergebnis.
Gemessen am 2026-09-28 kostet das im Export rund 45 Sekunden je Symbol; bei
knapp zweihundert Titeln ist es der groesste Einzelposten des Tageslaufs und
der Grund, aus dem er sein Zeitfenster nicht mehr schafft.

Dieser Vorrat reicht die Serien weiter, statt sie ein zweites Mal zu bauen.

**Er ist eine Abkuerzung, keine Quelle.** Was nicht darin liegt, wird
gerechnet wie bisher -- die Wiederholsperre (ADR 0054) nimmt der Analyse
taeglich ein paar Dutzend Titel ab, und die brauchen trotzdem einen Chart.
Ein Fehltreffer ist deshalb der Normalfall und kein Ausnahmezustand.

**Gefuellt wird nur, wenn beide Seiten dieselbe Quelle haben.** Die
Chartquelle liest ausdruecklich immer den Bestand und niemals einen
Anbieter (``bootstrap.build_chart_market_data``); lief die Analyse auf
Fixture-Daten oder direkt gegen die TWS, waeren ihre Serien andere. Darueber
entscheidet der Composition Root, nicht diese Klasse -- sie weiss nichts
ueber Konfiguration.
"""

from __future__ import annotations

from ai_trading_analyst.domain.screening import CandleSeries


class Kerzenvorrat:
    """Serien je Symbol, abgelegt von der Analyse, gelesen vom Export.

    Kein Zwischenspeicher ueber Laeufe hinweg: Der Vorrat lebt genau so
    lange wie ein Lauf. Ueber Tage hinweg waere er falsch -- jeder
    Handelstag bringt eine neue Kerze.

    Kostet keinen zusaetzlichen Speicher: Die Serien haelt der Lauf
    ohnehin bis zum Schluss, weil die Optionsanalyse in Phase 1b Kurs und
    Datum der Entscheidungskerze daraus nimmt (ADR 0069). Der Vorrat
    verweist auf dieselben Objekte.
    """

    def __init__(self) -> None:
        self._serien: dict[str, CandleSeries] = {}

    def lege_ab(self, symbol: str, serie: CandleSeries) -> None:
        self._serien[symbol] = serie

    def hole(self, symbol: str) -> CandleSeries | None:
        """Die Serie, falls der Lauf sie schon gerechnet hat."""
        return self._serien.get(symbol)

    def __len__(self) -> int:
        return len(self._serien)
