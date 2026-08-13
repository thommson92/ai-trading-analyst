"""Die Auswertung der Ratings-Sonde.

Der Abruf braucht einen Schluessel und ist nicht Gegenstand dieser Tests.
Geprueft wird, dass keine Analystenaussage in die Ausgabe geraet und dass
eine leere Antwort als solche gemeldet wird statt als Erfolg.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe_finnhub_ratings import beschreibe, value_shape


class TestWertform:
    def test_ein_kursziel_erscheint_nur_als_muster(self) -> None:
        """350 ist die lizenzgebundene Analystenaussage."""
        assert value_shape(350) == "999"
        assert value_shape(287.45) == "999.99"

    def test_ein_datum_erscheint_nur_als_muster(self) -> None:
        assert value_shape("2026-08-13") == "9999-99-99"

    def test_leere_werte_werden_benannt(self) -> None:
        assert value_shape("") == "(leer)"
        assert value_shape(None) == "AAAA"  # "None" -- immerhin kein Inhalt


class TestBeschreibung:
    def test_eine_liste_wird_am_ersten_eintrag_beschrieben(self) -> None:
        nutzlast = [
            {"buy": 20, "hold": 5, "sell": 1, "period": "2026-08-01"},
            {"buy": 19, "hold": 6, "sell": 1, "period": "2026-07-01"},
        ]
        ausgabe = "\n".join(beschreibe(nutzlast))
        assert "2 Eintraege" in ausgabe
        assert "buy" in ausgabe
        assert "20" not in ausgabe  # die Zahl selbst nicht

    def test_ein_objekt_wird_direkt_beschrieben(self) -> None:
        ausgabe = "\n".join(beschreibe({"targetMean": 350.0, "symbol": "AAPL"}))
        assert "targetMean" in ausgabe
        assert "350" not in ausgabe

    def test_eine_leere_liste_ist_ein_befund_kein_erfolg(self) -> None:
        """Erreichbar, aber ohne Daten -- das ist etwas anderes als
        'enthalten' und muss unterscheidbar bleiben."""
        assert "ohne Daten" in "\n".join(beschreibe([]))

    def test_eine_unbrauchbare_antwort_wird_benannt(self) -> None:
        assert "keine auswertbare Struktur" in "\n".join(beschreibe("Fehlertext"))
