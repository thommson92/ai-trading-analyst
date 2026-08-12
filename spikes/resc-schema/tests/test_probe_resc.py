"""Die reinen Auswertungsfunktionen der RESC-Sonde.

Der TWS-Abruf selbst ist nicht Gegenstand dieser Tests -- er braucht eine
laufende TWS. Geprueft wird das, worauf es fachlich ankommt: dass die
Zusammenfassung die Struktur vollstaendig zeigt und dabei keinen Inhalt
durchlaesst.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe_resc import summarize, value_shape

BEISPIEL = """
<REScreport>
  <Company ticker="AAPL">
    <CompanyName>Apple Inc</CompanyName>
  </Company>
  <EPSRecord unit="U">
    <EPSEstimate period="1">
      <ConsEstimate type="High">3.45</ConsEstimate>
      <ConsEstimate type="Low">2.90</ConsEstimate>
    </EPSEstimate>
  </EPSRecord>
  <Estimate>
    <ExpectedReportDate>2026-07-30</ExpectedReportDate>
  </Estimate>
</REScreport>
"""


class TestWertform:
    def test_ein_datum_wird_zum_muster(self) -> None:
        assert value_shape("2026-07-30") == "9999-99-99"

    def test_ein_name_wird_zum_muster(self) -> None:
        assert value_shape("Apple Inc") == "AAAAA AAA"

    def test_leerer_text_bleibt_leer(self) -> None:
        assert value_shape("\n   ") == ""

    def test_lange_laeufe_werden_gekuerzt(self) -> None:
        """Sonst stuende ein Analystenkommentar als Wand aus A in der Ausgabe."""
        assert value_shape("A" * 200) == "A{...}"

    def test_die_ausgabe_bleibt_auch_sonst_begrenzt(self) -> None:
        assert len(value_shape("ab12" * 100)) <= 60


class TestZusammenfassung:
    def test_jeder_pfad_erscheint_genau_einmal(self) -> None:
        pfade = [zeile.split("  ")[0] for zeile in summarize(BEISPIEL)]
        assert pfade == sorted(pfade)
        assert len(pfade) == len(set(pfade))

    def test_wiederholte_elemente_werden_gezaehlt_statt_wiederholt(self) -> None:
        treffer = [
            zeile
            for zeile in summarize(BEISPIEL)
            if zeile.startswith("REScreport/EPSRecord/EPSEstimate/ConsEstimate")
        ]
        assert len(treffer) == 1
        assert "(x2)" in treffer[0]

    def test_attributnamen_erscheinen_ohne_ihre_werte(self) -> None:
        zeile = next(z for z in summarize(BEISPIEL) if z.startswith("REScreport/Company "))
        assert "Attribute: ticker" in zeile
        assert "AAPL" not in zeile

    def test_kein_einziger_originalwert_steht_in_der_ausgabe(self) -> None:
        """Der eigentliche Zweck der Wertformen -- die Daten sind
        lizenzgebunden und gehoeren nicht in ein Protokoll."""
        ausgabe = "\n".join(summarize(BEISPIEL))
        for wert in ("Apple Inc", "3.45", "2.90", "2026-07-30", "AAPL"):
            assert wert not in ausgabe

    def test_ein_datumsfeld_ist_an_seiner_wertform_erkennbar(self) -> None:
        """Genau darum geht es: Enthaelt RESC einen Berichtstermin?"""
        zeile = next(z for z in summarize(BEISPIEL) if "ExpectedReportDate" in z)
        assert "9999-99-99" in zeile
