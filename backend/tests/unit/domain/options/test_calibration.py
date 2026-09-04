"""Tests des Kalibrierungs-Messlaufs (ADR 0058, Stufe 0).

Der Kern dieser Tests ist eine **konstruierte Kette mit bekannter Wahrheit**:
Notierungen, die exakt aus dem Modell stammen, mit einem eingebauten
Volatilitaetsaufschlag und einer eingebauten Skew-Steigung. Findet die
Messung beide zurueck, misst sie das Richtige. Ein Test gegen echte
Marktdaten koennte das nicht -- dort ist die Wahrheit unbekannt, und ein
Ergebnis saehe immer plausibel aus.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pytest

from ai_trading_analyst.domain.options import (
    TAGE_JE_JAHR,
    Observation,
    price_put,
    summarize_calibration,
    verteilung,
)

ZINS = 0.04
LAUFZEIT = 35 / TAGE_JE_JAHR
KURS = 100.0
KETTE = ("TEST", datetime(2026, 9, 4, 16, 45, tzinfo=UTC), date(2026, 10, 9))


AM_GELD = 0.30
REALISIERT = 0.24
"""Eine Kette hat **eine** realisierte Volatilitaet -- sie steht auf der
Kurshistorie des Symbols und nicht auf einem Strike. Der wahre Aufschlag
dieser Testkette ist damit ``0,30 / 0,24 = 1,25``."""


def _aus_dem_modell(
    strike: float,
    *,
    implizit: float,
    realisiert: float | None = REALISIERT,
    kette: tuple[str, datetime, date] = KETTE,
) -> Observation:
    """Eine Notierung, die exakt das Modell trifft -- die Wahrheit ist bekannt."""
    mid = price_put(
        spot=KURS,
        strike=strike,
        years_to_expiration=LAUFZEIT,
        volatility=implizit,
        risk_free_rate=ZINS,
    ).premium
    return Observation(
        symbol=kette[0],
        underlying_price=KURS,
        strike=strike,
        years_to_expiration=LAUFZEIT,
        quoted_mid=mid,
        quoted_implied_volatility=implizit,
        realized_volatility=realisiert,
        chain_key=kette,
    )


def _kette_mit_skew(
    steigung: float, *, kette: tuple[str, datetime, date] = KETTE
) -> list[Observation]:
    """Eine Kette mit bekanntem Niveau am Geld und bekannter Skew-Steigung."""
    return [
        _aus_dem_modell(
            strike,
            implizit=AM_GELD + steigung * math.log(strike / KURS),
            kette=kette,
        )
        for strike in (98.0, 95.0, 92.0, 89.0)
    ]


class TestBekannteWahrheit:
    def test_die_drei_messgroessen_kommen_zurueck(self) -> None:
        """Eine Kette mit eingebautem Aufschlag 1,25 und Skew -0,5."""
        steigung = -0.5

        ergebnis = summarize_calibration(_kette_mit_skew(steigung), risk_free_rate=ZINS)

        assert ergebnis.notierungen == 4
        assert ergebnis.formeltreue is not None
        assert ergebnis.formeltreue.median == pytest.approx(0.0, abs=1e-12)
        assert ergebnis.volatilitaetsaufschlag is not None
        assert ergebnis.volatilitaetsaufschlag.median == pytest.approx(
            AM_GELD / REALISIERT
        )
        assert ergebnis.skew_steigung is not None
        assert ergebnis.skew_steigung.median == pytest.approx(steigung)
        assert ergebnis.ketten == 1
        assert ergebnis.ketten_mit_gerade == 1

    @pytest.mark.parametrize("steigung", [0.0, -0.5, -1.0, -2.0])
    def test_der_aufschlag_bleibt_vom_skew_unberuehrt(self, steigung: float) -> None:
        """Der wichtigste Test dieses Moduls.

        Je **Notierung** gerechnet maesse der Aufschlag den Skew mit: Bei einem
        wahren Aufschlag von 1,25 kaeme mit einer Steigung von -0,5 der Wert
        1,49 heraus und mit -1,0 sogar 1,74 -- systematisch zu hoch, und
        abhaengig davon, welche Strikes der Tageslauf gerade notiert hat.
        Genau dieser Faktor soll spaeter einen Konfigurationswert ersetzen
        (ADR 0058, Festlegung 2); er darf nicht davon abhaengen, wie steil die
        Kurve gerade steht.
        """
        ergebnis = summarize_calibration(_kette_mit_skew(steigung), risk_free_rate=ZINS)

        assert ergebnis.volatilitaetsaufschlag is not None
        assert ergebnis.volatilitaetsaufschlag.median == pytest.approx(
            AM_GELD / REALISIERT
        )

    def test_ein_falscher_zins_zeigt_sich_in_der_formeltreue(self) -> None:
        """Der Sinn der Messung: Rechnet der Messlauf mit einer anderen
        Annahme als der Markt, faellt das auf und verschwindet nicht."""
        beobachtungen = [_aus_dem_modell(strike, implizit=AM_GELD) for strike in (95.0, 90.0)]

        richtig = summarize_calibration(beobachtungen, risk_free_rate=ZINS)
        falsch = summarize_calibration(beobachtungen, risk_free_rate=ZINS + 0.05)

        assert richtig.formeltreue is not None
        assert falsch.formeltreue is not None
        assert richtig.formeltreue.median == pytest.approx(0.0, abs=1e-12)
        assert abs(falsch.formeltreue.median) > 0.01


class TestFehlendeGrundlage:
    def test_ohne_implizite_volatilitaet_zaehlt_die_notierung_nur_mit(self) -> None:
        """Sie taucht in der Gesamtzahl auf und in keiner Messgroesse --
        nicht als Null (CLAUDE.md)."""
        vollstaendig = _aus_dem_modell(95.0, implizit=AM_GELD)
        ohne = Observation(
            symbol="TEST",
            underlying_price=KURS,
            strike=92.0,
            years_to_expiration=LAUFZEIT,
            quoted_mid=1.0,
            quoted_implied_volatility=None,
            realized_volatility=0.24,
            chain_key=KETTE,
        )

        ergebnis = summarize_calibration([vollstaendig, ohne], risk_free_rate=ZINS)

        assert ergebnis.notierungen == 2
        assert ergebnis.ohne_implizite_volatilitaet == 1
        assert ergebnis.formeltreue is not None
        assert ergebnis.formeltreue.anzahl == 1

    def test_ohne_realisierte_volatilitaet_faellt_nur_der_aufschlag_aus(self) -> None:
        """Die Formeltreue braucht sie nicht -- sie rechnet mit der notierten
        impliziten. Beide Groessen fallen getrennt aus, wie sie getrennt
        gemessen werden."""
        beobachtung = Observation(
            symbol="TEST",
            underlying_price=KURS,
            strike=95.0,
            years_to_expiration=LAUFZEIT,
            quoted_mid=1.5,
            quoted_implied_volatility=0.30,
            realized_volatility=None,
            chain_key=KETTE,
        )

        ergebnis = summarize_calibration([beobachtung], risk_free_rate=ZINS)

        assert ergebnis.ohne_realisierte_volatilitaet == 1
        assert ergebnis.volatilitaetsaufschlag is None
        assert ergebnis.formeltreue is not None

    def test_ohne_notierungen_bleibt_alles_leer(self) -> None:
        ergebnis = summarize_calibration([], risk_free_rate=ZINS)

        assert ergebnis.notierungen == 0
        assert ergebnis.formeltreue is None
        assert ergebnis.volatilitaetsaufschlag is None
        assert ergebnis.skew_steigung is None


class TestSkew:
    def test_zwei_punkte_ergeben_keine_steigung(self) -> None:
        """Zwei Punkte legen immer eine Gerade und sagen damit nichts darueber,
        ob es eine gibt."""
        beobachtungen = [_aus_dem_modell(strike, implizit=AM_GELD) for strike in (95.0, 90.0)]

        ergebnis = summarize_calibration(beobachtungen, risk_free_rate=ZINS)

        assert ergebnis.skew_steigung is None
        assert ergebnis.ketten_mit_gerade == 0

    def test_zwei_ketten_werden_getrennt_geschaetzt(self) -> None:
        """Ueber beide zusammen gerechnet vermengte die Schaetzung die Form der
        Kurve mit dem Niveauunterschied zwischen den Ketten."""
        zweite = ("ZWEIT", datetime(2026, 9, 5, 16, 45, tzinfo=UTC), date(2026, 10, 9))
        flach = [
            _aus_dem_modell(strike, implizit=AM_GELD) for strike in (98.0, 95.0, 92.0)
        ]
        steil = [
            _aus_dem_modell(
                strike, implizit=0.60 - 1.0 * math.log(strike / KURS), kette=zweite
            )
            for strike in (98.0, 95.0, 92.0)
        ]

        ergebnis = summarize_calibration([*flach, *steil], risk_free_rate=ZINS)

        assert ergebnis.ketten_mit_gerade == 2
        assert ergebnis.skew_steigung is not None
        assert ergebnis.skew_steigung.kleinster == pytest.approx(-1.0)
        assert ergebnis.skew_steigung.groesster == pytest.approx(0.0, abs=1e-12)

    def test_gleiche_strikes_ergeben_keine_steigung(self) -> None:
        """Alle Punkte auf demselben ``x``: Die Steigung ist nicht bestimmt,
        und eine Zahl waere hier erfunden."""
        beobachtungen = [_aus_dem_modell(95.0, implizit=iv) for iv in (0.28, 0.30, 0.32)]

        ergebnis = summarize_calibration(beobachtungen, risk_free_rate=ZINS)

        assert ergebnis.skew_steigung is None


class TestVerteilung:
    def test_eine_leere_reihe_hat_keine_verteilung(self) -> None:
        assert verteilung([]) is None

    def test_ein_einziger_wert_ist_seine_eigene_verteilung(self) -> None:
        """``statistics.quantiles`` braucht zwei Werte. Ein einzelner ist
        trotzdem eine Aussage -- und Median wie Quartile sind dann er selbst."""
        einzeln = verteilung([2.5])

        assert einzeln is not None
        assert einzeln.anzahl == 1
        assert einzeln.median == pytest.approx(2.5)
        assert einzeln.unteres_quartil == pytest.approx(2.5)
        assert einzeln.groesster == pytest.approx(2.5)

    def test_ausreisser_verschieben_den_median_nicht(self) -> None:
        """Der Grund fuer Median und Quartile statt Mittelwert und Streuung:
        Eine Notierung aus einem gekreuzten Markt soll die Reihe nicht
        schlechter aussehen lassen, als sie ist."""
        sauber = verteilung([1.0, 1.1, 1.2, 1.3, 1.4])
        mit_ausreisser = verteilung([1.0, 1.1, 1.2, 1.3, 1.4, 99.0])

        assert sauber is not None
        assert mit_ausreisser is not None
        assert abs(mit_ausreisser.median - sauber.median) < 0.11
        assert mit_ausreisser.groesster == pytest.approx(99.0)


class TestFehlenderMittelwert:
    """Der haeufigste Ausfall: Nach Boersenschluss und bei duennen Kontrakten
    liefert IBKR regelmaessig nur eine Seite (``OptionQuote.mid``)."""

    @staticmethod
    def _ohne_mittelwert(strike: float) -> Observation:
        return Observation(
            symbol="TEST",
            underlying_price=KURS,
            strike=strike,
            years_to_expiration=LAUFZEIT,
            quoted_mid=None,
            quoted_implied_volatility=AM_GELD,
            realized_volatility=REALISIERT,
            chain_key=KETTE,
        )

    def test_er_wird_gezaehlt_statt_stillschweigend_zu_fehlen(self) -> None:
        """Ohne diese Zahl bliebe die Luecke zwischen ``notierungen`` und der
        Zahl der Formeltreue-Werte unerklaerlich -- und die Abdeckung ist
        genau die Frage, fuer die der Messlauf gebaut ist."""
        ergebnis = summarize_calibration(
            [_aus_dem_modell(95.0, implizit=AM_GELD), self._ohne_mittelwert(92.0)],
            risk_free_rate=ZINS,
        )

        assert ergebnis.notierungen == 2
        assert ergebnis.ohne_mittelwert == 1
        assert ergebnis.formeltreue is not None
        assert ergebnis.formeltreue.anzahl == 1

    def test_er_verfaelscht_die_formeltreue_nicht(self) -> None:
        """Wuerde der fehlende Mittelwert als 0,0 einfliessen, waere die
        relative Abweichung eine Division durch null oder -- schlimmer -- eine
        gewaltige Zahl, die den Median kippte."""
        ergebnis = summarize_calibration(
            [*_kette_mit_skew(-0.5), self._ohne_mittelwert(80.0)],
            risk_free_rate=ZINS,
        )

        assert ergebnis.formeltreue is not None
        assert ergebnis.formeltreue.median == pytest.approx(0.0, abs=1e-12)

    def test_zur_skew_kurve_traegt_er_trotzdem_bei(self) -> None:
        """Die implizite Volatilitaet steht auch ohne Geld- und Briefkurs am
        Kontrakt -- fuer Skew und Aufschlag ist die Notierung brauchbar."""
        ergebnis = summarize_calibration(
            [
                self._ohne_mittelwert(98.0),
                self._ohne_mittelwert(95.0),
                self._ohne_mittelwert(92.0),
            ],
            risk_free_rate=ZINS,
        )

        assert ergebnis.formeltreue is None
        assert ergebnis.ketten_mit_gerade == 1
        assert ergebnis.volatilitaetsaufschlag is not None


class TestGeradeBrauchtDreiStrikes:
    def test_drei_notierungen_auf_zwei_strikes_genuegen_nicht(self) -> None:
        """Die Steigung kaeme dann faktisch aus zwei Stuetzstellen -- genau die
        Tautologie, gegen die die Schranke gesetzt ist."""
        ergebnis = summarize_calibration(
            [
                _aus_dem_modell(95.0, implizit=0.30),
                _aus_dem_modell(95.0, implizit=0.31),
                _aus_dem_modell(90.0, implizit=0.33),
            ],
            risk_free_rate=ZINS,
        )

        assert ergebnis.ketten == 1
        assert ergebnis.ketten_mit_gerade == 0
        assert ergebnis.skew_steigung is None
        assert ergebnis.volatilitaetsaufschlag is None


class TestZweiWerte:
    def test_die_quartile_bleiben_in_der_spanne(self) -> None:
        """``statistics.quantiles`` extrapoliert in der Vorgabemethode ueber
        die Reihe hinaus: Aus ``[0, 10]`` wuerden die Quartile -2,5 und 12,5.
        Ein negatives Quartil neben einem Aufschlag, der nur positiv sein
        kann, waere sichtbar falsch -- und die duenne Anfangslage ist genau
        der Fall, den ADR 0058 als Risiko benennt."""
        zwei = verteilung([0.0, 10.0])

        assert zwei is not None
        assert zwei.kleinster <= zwei.unteres_quartil <= zwei.median
        assert zwei.median <= zwei.oberes_quartil <= zwei.groesster
        assert zwei.unteres_quartil == pytest.approx(2.5)
        assert zwei.oberes_quartil == pytest.approx(7.5)

    @pytest.mark.parametrize("anzahl", [2, 3, 4, 5])
    def test_die_quartile_verlassen_die_spanne_nie(self, anzahl: int) -> None:
        werte = [float(i) for i in range(anzahl)]

        ergebnis = verteilung(werte)

        assert ergebnis is not None
        assert ergebnis.kleinster <= ergebnis.unteres_quartil
        assert ergebnis.oberes_quartil <= ergebnis.groesster
