"""Die Kurzfassung aus dem gespeicherten Dokument (ADR 0062)."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.options import OptionsStatus
from ai_trading_analyst.domain.report import as_document, build_report, extract_summary_fields
from tests.unit.domain.report.conftest import (
    make_earnings,
    make_options,
    make_outcome,
    make_technical,
)

ERSTELLT = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)


def dokument(**overrides: object) -> dict:  # type: ignore[type-arg]
    return as_document(
        build_report(make_outcome(**overrides), created_at=ERSTELLT, app_version="0.1.0")
    )


class TestVollstaendigerBericht:
    def test_liest_signale_earnings_technik_und_put(self) -> None:
        kurz = extract_summary_fields(
            dokument(
                earnings=make_earnings(EarningsFilterStatus.EARNINGS_CLEAR),
                technical=make_technical(),
                options=make_options(),
            )
        )
        # A = RSI_CROSS, C = EMA5_EMA20_CROSS -- dieselbe Zuordnung wie im Backtest.
        assert kurz.signal_letters == "AC"
        assert kurz.earnings_status == "EARNINGS_CLEAR"
        assert kurz.earnings_next_date == "2026-11-01"
        assert kurz.options_status == "COMPLETED"
        assert kurz.put_suggestion is not None
        assert kurz.put_suggestion.strike == 320.0
        assert kurz.put_suggestion.premium == 2.30
        assert kurz.put_suggestion.expiration == "2026-10-16"
        assert kurz.put_suggestion.days_to_expiration == 45
        assert kurz.close is not None
        assert kurz.decision_candle_at is not None


class TestKargerBericht:
    def test_ohne_module_bleibt_alles_leer_ausser_den_signalen(self) -> None:
        """Kein Ersatzwert: Was der Bericht nicht sagt, sagt die Kurzfassung
        auch nicht."""
        kurz = extract_summary_fields(dokument())
        assert kurz.signal_letters == "AC"
        assert kurz.earnings_status is None
        assert kurz.put_suggestion is None
        assert kurz.options_status is None
        assert kurz.close is None
        assert kurz.company_name is None

    def test_ein_optionsergebnis_ohne_vorschlag_nennt_status_und_grund(self) -> None:
        kurz = extract_summary_fields(
            dokument(options=make_options(status=OptionsStatus.INSUFFICIENT_DATA))
        )
        assert kurz.options_status == "INSUFFICIENT_DATA"
        assert kurz.put_suggestion is None


class TestFremdeDokumente:
    def test_ein_leeres_dokument_ergibt_lauter_none(self) -> None:
        kurz = extract_summary_fields({})
        assert kurz.signal_letters is None
        assert kurz.put_suggestion is None

    def test_ein_unbekannter_signaltyp_wird_uebergangen_nicht_geraten(self) -> None:
        doc = dokument()
        doc["abschnitte"]["TECHNISCHE_SIGNALE"]["inhalt"].append(
            {"signal_type": "AUS_DER_ZUKUNFT", "candle_index": 1}
        )
        assert extract_summary_fields(doc).signal_letters == "AC"

    def test_ein_vorschlag_ohne_kerngroessen_ist_keiner(self) -> None:
        doc = dokument(options=make_options())
        doc["abschnitte"]["PUT_STRATEGIEN"]["inhalt"]["vorschlaege"][0].pop("strike")
        assert extract_summary_fields(doc).put_suggestion is None
