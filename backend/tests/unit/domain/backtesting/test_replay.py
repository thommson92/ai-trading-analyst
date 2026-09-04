"""Tests des historischen Replays (G1-Pruefvorlage Abschnitt 4.1)."""

from __future__ import annotations

from ai_trading_analyst.domain.backtesting.replay import (
    HistoricalDecision,
    find_historical_decisions,
    group_into_episodes,
)
from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    IndicatorValues,
    SignalEvent,
    SignalType,
)

from .conftest import BASELINE_EMA, RSI_AND_EMA_CROSS_FIRE, make_series

PARAMS = CandidateRuleParameters(
    required_crossing_signals=2, signal_lookback_previous_candles=5, warmup_candles=10
)
EXPECTED_COMBINATION = frozenset(
    {
        SignalType.RSI_CROSS,
        SignalType.EMA5_EMA20_CROSS,
        # Die ruhige Baseline enthaelt kein Abwaertskreuz, also ist das
        # Ausschlusskriterium erfuellt -- es steht in jeder Kombination mit.
        SignalType.NO_RECENT_EMA_DOWNCROSS,
    }
)


class TestEntscheidungszeitpunkte:
    def test_nur_die_erste_tageskerze_ist_ein_entscheidungspunkt(self) -> None:
        # Index 30 ist gerade (erste Tageskerze), 31 ungerade (zweite).
        series = make_series(
            40,
            indicator_overrides={30: RSI_AND_EMA_CROSS_FIRE, 31: RSI_AND_EMA_CROSS_FIRE},
        )
        decisions = find_historical_decisions(series, PARAMS)
        indices = {decision.index for decision in decisions}
        assert 30 in indices
        assert 31 not in indices

    def test_ein_signal_auf_der_zweiten_tageskerze_wirkt_in_ein_spaeteres_fenster(self) -> None:
        """Index 29 (zweite Tageskerze) liegt im Sechs-Kerzen-Fenster von
        Index 34 (29 = 34 - 5) und zaehlt dort mit.

        Allein traegt es die Qualifikation seit ADR 0057 aber nicht mehr: Die
        Torbedingung der Frische verlangt ein Kaufsignal auf ``t`` oder
        ``t-1``. Erst ein frisches zweites Signal auf 34 macht den
        Entscheidungspunkt -- und dass daraus zwei Kaufsignale werden, ist
        genau der Beitrag des alten.
        """
        nur_alt = make_series(40, indicator_overrides={29: RSI_AND_EMA_CROSS_FIRE})
        assert 34 not in {d.index for d in find_historical_decisions(nur_alt, PARAMS)}

        mit_frischem = make_series(
            40,
            indicator_overrides={
                29: RSI_AND_EMA_CROSS_FIRE,
                34: IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=110.0, ema20=BASELINE_EMA),
            },
        )
        entscheidungen = {
            d.index: d.combination for d in find_historical_decisions(mit_frischem, PARAMS)
        }
        assert 34 in entscheidungen
        assert SignalType.RSI_CROSS in entscheidungen[34]

    def test_gefundene_kombination_entspricht_den_gefeuerten_signaltypen(self) -> None:
        series = make_series(40, indicator_overrides={30: RSI_AND_EMA_CROSS_FIRE})
        decisions = find_historical_decisions(series, PARAMS)
        by_index = {d.index: d.combination for d in decisions}
        assert by_index[30] == EXPECTED_COMBINATION

    def test_keine_qualifikation_ergibt_keine_entscheidungen(self) -> None:
        series = make_series(40)
        assert find_historical_decisions(series, PARAMS) == ()


class TestEpisodenbildung:
    """Geteilte Signalereignisse buendeln, nicht zeitliche Naehe (ADR 0057)."""

    @staticmethod
    def _entscheidung(index: int, *ereignisse: tuple[SignalType, int]) -> HistoricalDecision:
        return HistoricalDecision(
            index=index,
            combination=EXPECTED_COMBINATION,
            signal_firings=frozenset(
                SignalEvent(signal_type=typ, candle_index=kerze) for typ, kerze in ereignisse
            ),
        )

    def test_ein_geteiltes_ereignis_buendelt(self) -> None:
        kreuzung = (SignalType.RSI_CROSS, 8)
        episoden = group_into_episodes(
            [
                self._entscheidung(10, kreuzung),
                self._entscheidung(12, kreuzung, (SignalType.EMA5_EMA20_CROSS, 11)),
            ]
        )
        assert [[e.index for e in episode] for episode in episoden] == [[10, 12]]

    def test_ohne_geteiltes_ereignis_bleiben_es_zwei(self) -> None:
        """Zeitlich dicht, aber auf eigener Grundlage -- der Fall aus
        ``docs/backtesting/Gruppierung.png``, zweiter Block."""
        episoden = group_into_episodes(
            [
                self._entscheidung(10, (SignalType.RSI_CROSS, 8)),
                self._entscheidung(12, (SignalType.RSI_CROSS, 12)),
            ]
        )
        assert [[e.index for e in episode] for episode in episoden] == [[10], [12]]

    def test_die_kette_reicht_ueber_den_direkten_nachbarn_hinaus(self) -> None:
        """Der dritte Punkt teilt nichts mehr mit dem ersten, wohl aber mit
        dem zweiten -- alle drei sind eine Episode."""
        episoden = group_into_episodes(
            [
                self._entscheidung(10, (SignalType.RSI_CROSS, 8)),
                self._entscheidung(
                    12, (SignalType.RSI_CROSS, 8), (SignalType.EMA5_EMA20_CROSS, 11)
                ),
                self._entscheidung(14, (SignalType.EMA5_EMA20_CROSS, 11)),
            ]
        )
        assert [[e.index for e in episode] for episode in episoden] == [[10, 12, 14]]

    def test_grosser_abstand_trennt_nicht_wenn_die_grundlage_dieselbe_ist(self) -> None:
        """Der Gegenentwurf zum frueheren Cooldown: Er haette hier getrennt."""
        kreuzung = (SignalType.RSI_CROSS, 8)
        episoden = group_into_episodes(
            [self._entscheidung(10, kreuzung), self._entscheidung(13, kreuzung)]
        )
        assert len(episoden) == 1

    def test_das_ausschlusskriterium_verkettet_nie(self) -> None:
        """Es traegt immer die eigene Entscheidungskerze und sagt damit nichts
        ueber gemeinsame Grundlage."""
        episoden = group_into_episodes(
            [
                self._entscheidung(10, (SignalType.NO_RECENT_EMA_DOWNCROSS, 10)),
                self._entscheidung(12, (SignalType.NO_RECENT_EMA_DOWNCROSS, 12)),
            ]
        )
        assert len(episoden) == 2

    def test_leere_liste_bleibt_leer(self) -> None:
        assert group_into_episodes([]) == ()

    def test_eine_aeltere_fundstelle_im_fenster_zerreisst_die_episode_nicht(self) -> None:
        """Der Fall, an dem die gespeicherte fruehste Fundstelle scheitert.

        Dieselbe Kreuzung feuert auf 26, 29 und 32. Die Fenster:

        * 30 sieht ``[25..30]`` -- Feuerungen auf 26 und 29
        * 32 sieht ``[27..32]`` -- Feuerungen auf 29 und 32

        Beide werten die Kreuzung auf **29** aus, gehoeren also zusammen.
        ``signal_events`` fuehrte aber je Typ nur die fruehste Fundstelle: 26
        beim einen, 29 beim anderen -- der Schnitt waere leer und die Episode
        zerfiele in zwei. ``signal_firings`` fuehrt jede Feuerung und findet
        die geteilte Grundlage.
        """
        series = make_series(
            40,
            indicator_overrides={
                26: RSI_AND_EMA_CROSS_FIRE,
                29: RSI_AND_EMA_CROSS_FIRE,
                32: RSI_AND_EMA_CROSS_FIRE,
            },
        )
        entscheidungen = find_historical_decisions(series, PARAMS)
        assert [d.index for d in entscheidungen] == [26, 30, 32]

        episoden = group_into_episodes(entscheidungen)
        assert [[e.index for e in episode] for episode in episoden] == [[26, 30, 32]]
