"""Umgewichtung, Untergrenze und Begruendung (Doc 09 "Fehlende Komponenten").

Der Kern der Zusicherung: **Eine fehlende Komponente geht nie mit 0 ein.**
Sie zu bewerten hiesse zu behaupten, sie sei geprueft und schlecht -- und
das waere ein erfundener Wert an der Stelle, an der das System am
sichtbarsten ist.
"""

from __future__ import annotations

import pytest

from ai_trading_analyst.domain.scoring import (
    ComponentName,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
    aggregate,
)
from ai_trading_analyst.domain.scoring.aggregate import _BEZEICHNUNG


def rechne(
    *komponenten: ScoreComponent,
    minimum: float = 0.6,
    normal: float = 0.8,
    risiken: tuple[str, ...] = (),
) -> ScoreResult:
    return aggregate(
        kind=ScoreKind.LONG_TERM,
        version="1.0",
        components=komponenten,
        minimum_coverage=minimum,
        normal_confidence_coverage=normal,
        limiting_risks=risiken,
    )


def komponente(name: ComponentName, gewicht: float, wert: float | None) -> ScoreComponent:
    return ScoreComponent(name=name, weight=gewicht, value=wert, reason="aus dem Test")


VOLLSTAENDIG = (
    komponente(ComponentName.PROFITABILITY, 0.30, 9.0),
    komponente(ComponentName.GROWTH, 0.25, 6.0),
    komponente(ComponentName.VALUATION, 0.25, 4.0),
    komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, 8.0),
)


class TestVollstaendigeRechnung:
    def test_der_gesamtwert_ist_das_gewichtete_mittel(self) -> None:
        # 0,30*9 + 0,25*6 + 0,25*4 + 0,20*8 = 2,7 + 1,5 + 1,0 + 1,6 = 6,8
        assert rechne(*VOLLSTAENDIG).value == 6.8

    def test_die_abdeckung_ist_voll_und_die_konfidenz_normal(self) -> None:
        ergebnis = rechne(*VOLLSTAENDIG)
        assert ergebnis.coverage == 1.0
        assert ergebnis.confidence is ScoreConfidence.NORMAL
        assert ergebnis.status is ScoreStatus.COMPLETED

    def test_die_wirksamen_gewichte_entsprechen_den_konfigurierten(self) -> None:
        ergebnis = rechne(*VOLLSTAENDIG)
        assert [k.effective_weight for k in ergebnis.components] == [0.30, 0.25, 0.25, 0.20]


class TestUmgewichtung:
    def test_die_uebrigen_gewichte_werden_auf_hundert_prozent_normiert(self) -> None:
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 10.0),
            komponente(ComponentName.GROWTH, 0.25, 5.0),
            komponente(ComponentName.VALUATION, 0.25, 5.0),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, None),
        )
        assert ergebnis.coverage == pytest.approx(0.8)
        gewichte = {k.name: k.effective_weight for k in ergebnis.components}
        assert gewichte[ComponentName.PROFITABILITY] == pytest.approx(0.375)
        assert sum(gewichte.values()) == pytest.approx(1.0)

    def test_die_fehlende_komponente_bekommt_kein_gewicht_und_keinen_wert(self) -> None:
        """Der eigentliche Befund: Sie geht nicht mit 0 ein, sondern gar
        nicht. Mit 0 laege der Gesamtwert unten bei 5,5 statt bei 6,9."""
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 10.0),
            komponente(ComponentName.GROWTH, 0.25, 5.0),
            komponente(ComponentName.VALUATION, 0.25, 5.0),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, None),
        )
        (fehlend,) = [k for k in ergebnis.components if not k.available]
        assert fehlend.effective_weight == 0.0
        assert fehlend.value is None
        assert ergebnis.value == 6.9
        assert ergebnis.missing_components == (ComponentName.BALANCE_SHEET_QUALITY,)

    def test_das_konfigurierte_gewicht_bleibt_sichtbar(self) -> None:
        """Damit im Bericht steht, wie viel Gewicht die Luecke gekostet hat."""
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 10.0),
            komponente(ComponentName.GROWTH, 0.25, 5.0),
            komponente(ComponentName.VALUATION, 0.25, 5.0),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, None),
        )
        (fehlend,) = [k for k in ergebnis.components if not k.available]
        assert fehlend.weight == 0.20


class TestUntergrenze:
    def test_bei_fuenfundfuenfzig_prozent_entsteht_kein_score(self) -> None:
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 10.0),
            komponente(ComponentName.GROWTH, 0.25, 10.0),
            komponente(ComponentName.VALUATION, 0.25, None),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, None),
        )
        assert ergebnis.coverage == pytest.approx(0.55)
        assert ergebnis.status is ScoreStatus.INSUFFICIENT_DATA
        assert ergebnis.value is None
        assert ergebnis.confidence is ScoreConfidence.INSUFFICIENT_DATA

    def test_bei_fuenfundsechzig_prozent_entsteht_einer(self) -> None:
        """Die Gegenprobe zur Untergrenze: Ohne sie liesse sich nicht
        unterscheiden, ob die Grenze wirkt oder ob nie ein Score entsteht."""
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 10.0),
            komponente(ComponentName.GROWTH, 0.25, 10.0),
            komponente(ComponentName.VALUATION, 0.25, None),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, 10.0),
        )
        assert ergebnis.coverage == pytest.approx(0.75)
        assert ergebnis.status is ScoreStatus.COMPLETED
        assert ergebnis.value == 10.0

    def test_ohne_score_bleiben_auch_die_wirksamen_gewichte_leer(self) -> None:
        """Es wurde nichts gerechnet -- ein umgewichtetes Gewicht daneben
        saehe aus wie eine halbe Rechnung."""
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 10.0),
            komponente(ComponentName.GROWTH, 0.25, None),
            komponente(ComponentName.VALUATION, 0.25, None),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, None),
        )
        assert all(k.effective_weight == 0.0 for k in ergebnis.components)

    def test_die_unterschreitung_wird_als_begrenzendes_risiko_ausgewiesen(self) -> None:
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 10.0),
            komponente(ComponentName.GROWTH, 0.25, None),
            komponente(ComponentName.VALUATION, 0.25, None),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, None),
        )
        assert any("Untergrenze" in risiko for risiko in ergebnis.limiting_risks)

    def test_uebergebene_begrenzungen_gehen_dabei_nicht_verloren(self) -> None:
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 10.0),
            komponente(ComponentName.GROWTH, 0.25, None),
            komponente(ComponentName.VALUATION, 0.25, None),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, None),
            risiken=("Stichprobe zu duenn",),
        )
        assert "Stichprobe zu duenn" in ergebnis.limiting_risks


class TestKonfidenz:
    def test_unter_der_normalgrenze_ist_die_konfidenz_eingeschraenkt(self) -> None:
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 8.0),
            komponente(ComponentName.GROWTH, 0.25, 8.0),
            komponente(ComponentName.VALUATION, 0.25, None),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, 8.0),
        )
        assert ergebnis.coverage == pytest.approx(0.75)
        assert ergebnis.confidence is ScoreConfidence.LOW_COVERAGE

    def test_auf_der_normalgrenze_ist_sie_normal(self) -> None:
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 8.0),
            komponente(ComponentName.GROWTH, 0.25, 8.0),
            komponente(ComponentName.VALUATION, 0.25, 8.0),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, None),
        )
        assert ergebnis.coverage == pytest.approx(0.8)
        assert ergebnis.confidence is ScoreConfidence.NORMAL


class TestBegruendung:
    def test_die_faktoren_stimmen_mit_den_teilwerten_ueberein(self) -> None:
        """Doc 10, Paragraph 6.11: "Die Begruendung muss mit den Teilwerten
        uebereinstimmen." Sie werden aus ihnen gerechnet, damit das nicht
        auseinanderlaufen kann."""
        ergebnis = rechne(*VOLLSTAENDIG)
        assert ergebnis.positive_factors == ("Profitabilitaet: 9.0", "Bilanzqualitaet: 8.0")
        assert ergebnis.negative_factors == ("Bewertung: 4.0",)

    def test_eine_mittlere_komponente_ist_weder_positiv_noch_negativ(self) -> None:
        ergebnis = rechne(*VOLLSTAENDIG)
        genannt = " ".join(ergebnis.positive_factors + ergebnis.negative_factors)
        assert "Wachstum" not in genannt

    def test_eine_fehlende_komponente_taucht_in_keiner_der_beiden_listen_auf(self) -> None:
        """Sonst laese sich eine Luecke als schwacher Wert."""
        ergebnis = rechne(
            komponente(ComponentName.PROFITABILITY, 0.30, 9.0),
            komponente(ComponentName.GROWTH, 0.25, 9.0),
            komponente(ComponentName.VALUATION, 0.25, 9.0),
            komponente(ComponentName.BALANCE_SHEET_QUALITY, 0.20, None),
        )
        genannt = " ".join(ergebnis.positive_factors + ergebnis.negative_factors)
        assert "Bilanzqualitaet" not in genannt

    def test_jede_komponente_hat_eine_deutsche_bezeichnung(self) -> None:
        """Eine fehlende fiele sonst erst im Bericht auf, und zwar als
        ``KeyError`` mitten im Zusammenstellen."""
        assert set(_BEZEICHNUNG) == set(ComponentName)


class TestUnmoegliches:
    def test_ein_score_ohne_komponenten_ist_keiner(self) -> None:
        with pytest.raises(ValueError, match="ohne Komponenten"):
            rechne()

    def test_gewichte_von_null_sind_ein_fehler(self) -> None:
        with pytest.raises(ValueError, match="summieren"):
            rechne(komponente(ComponentName.GROWTH, 0.0, 5.0))
