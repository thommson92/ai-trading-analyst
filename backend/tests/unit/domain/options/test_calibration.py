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


def _aus_dem_modell(
    strike: float,
    *,
    implizit: float,
    aufschlag: float = 1.25,
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
        realized_volatility=implizit / aufschlag,
        chain_key=kette,
    )


class TestBekannteWahrheit:
    def test_die_drei_messgroessen_kommen_zurueck(self) -> None:
        """Eine Kette mit eingebautem Aufschlag 1,25 und Skew -0,5."""
        steigung = -0.5
        beobachtungen = [
            _aus_dem_modell(
                strike, implizit=0.30 + steigung * math.log(strike / KURS)
            )
            for strike in (98.0, 95.0, 92.0, 89.0)
        ]

        ergebnis = summarize_calibration(beobachtungen, risk_free_rate=ZINS)

        assert ergebnis.notierungen == 4
        assert ergebnis.formeltreue is not None
        assert ergebnis.formeltreue.median == pytest.approx(0.0, abs=1e-12)
        assert ergebnis.volatilitaetsaufschlag is not None
        assert ergebnis.volatilitaetsaufschlag.median == pytest.approx(1.25)
        assert ergebnis.skew_steigung is not None
        assert ergebnis.skew_steigung.median == pytest.approx(steigung)
        assert ergebnis.ketten_fuer_skew == 1

    def test_ein_falscher_zins_zeigt_sich_in_der_formeltreue(self) -> None:
        """Der Sinn der Messung: Rechnet der Messlauf mit einer anderen
        Annahme als der Markt, faellt das auf und verschwindet nicht."""
        beobachtungen = [_aus_dem_modell(strike, implizit=0.30) for strike in (95.0, 90.0)]

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
        vollstaendig = _aus_dem_modell(95.0, implizit=0.30)
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
        beobachtungen = [_aus_dem_modell(strike, implizit=0.30) for strike in (95.0, 90.0)]

        ergebnis = summarize_calibration(beobachtungen, risk_free_rate=ZINS)

        assert ergebnis.skew_steigung is None
        assert ergebnis.ketten_fuer_skew == 0

    def test_zwei_ketten_werden_getrennt_geschaetzt(self) -> None:
        """Ueber beide zusammen gerechnet vermengte die Schaetzung die Form der
        Kurve mit dem Niveauunterschied zwischen den Ketten."""
        zweite = ("ZWEIT", datetime(2026, 9, 5, 16, 45, tzinfo=UTC), date(2026, 10, 9))
        flach = [
            _aus_dem_modell(strike, implizit=0.30) for strike in (98.0, 95.0, 92.0)
        ]
        steil = [
            _aus_dem_modell(
                strike, implizit=0.60 - 1.0 * math.log(strike / KURS), kette=zweite
            )
            for strike in (98.0, 95.0, 92.0)
        ]

        ergebnis = summarize_calibration([*flach, *steil], risk_free_rate=ZINS)

        assert ergebnis.ketten_fuer_skew == 2
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
