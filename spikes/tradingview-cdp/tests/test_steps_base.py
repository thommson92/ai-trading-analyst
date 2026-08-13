from __future__ import annotations

import pytest

from tvcdp.steps.base import StepStatus, run_step


class TestRunStep:
    async def test_erfolgreicher_schritt_ohne_explizites_status_gilt_als_passed(self) -> None:
        async def func() -> dict[str, object]:
            return {"value": 42}

        result = await run_step("s1", "Beispiel", func)

        assert result.status is StepStatus.PASSED
        assert result.details == {"value": 42}
        assert result.error is None

    async def test_expliziter_status_wird_uebernommen_und_aus_details_entfernt(self) -> None:
        async def func() -> dict[str, object]:
            return {"_status": StepStatus.INCONCLUSIVE.value, "reason": "keine Sonde konfiguriert"}

        result = await run_step("s2", "Beispiel", func)

        assert result.status is StepStatus.INCONCLUSIVE
        assert result.details == {"reason": "keine Sonde konfiguriert"}

    async def test_ausnahme_wird_zu_failed_mit_lesbarer_fehlermeldung(self) -> None:
        async def func() -> dict[str, object]:
            raise ValueError("etwas Konkretes ist schiefgelaufen")

        result = await run_step("s3", "Beispiel", func)

        assert result.status is StepStatus.FAILED
        assert result.error is not None
        assert "ValueError" in result.error
        assert "etwas Konkretes ist schiefgelaufen" in result.error

    async def test_duration_seconds_ist_nicht_negativ(self) -> None:
        async def func() -> dict[str, object]:
            return {}

        result = await run_step("s4", "Beispiel", func)

        assert result.duration_seconds >= 0

    @pytest.mark.parametrize("invalid_status", ["UNBEKANNT", "passed", ""])
    async def test_unbekannter_status_wert_schlaegt_fehl_statt_ihn_stillschweigend_zu_ignorieren(
        self, invalid_status: str
    ) -> None:
        async def func() -> dict[str, object]:
            return {"_status": invalid_status}

        result = await run_step("s5", "Beispiel", func)

        # Ein ungueltiger Statuswert loest in StepStatus(...) einen ValueError
        # aus, der von run_step als FAILED abgefangen wird -- kein Schritt
        # darf einen falsch geschriebenen Status als "irgendwie bestanden"
        # durchrutschen lassen.
        assert result.status is StepStatus.FAILED
