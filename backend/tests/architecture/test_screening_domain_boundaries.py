"""Dedizierter Architekturtest fuer den deterministischen Signalkern (Sprint 1A).

Ergaenzt ``test_layer_boundaries.py`` um eine explizit auf
``domain/screening`` zugeschnittene Pruefung: Sprint 1A verlangt ausdruecklich
den Nachweis, dass der Signalkern ohne Abhaengigkeit zu Infrastructure,
FastAPI, SQLAlchemy oder einem konkreten Datenanbieter auskommt. Die generelle
Schichtregel in ``test_layer_boundaries.py`` deckt das bereits ab (der
Signalkern liegt im Domain Layer); dieser Test macht die Anforderung
zusaetzlich lokal und unabhaengig von einer Aenderung dort nachvollziehbar.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.architecture.test_layer_boundaries import FORBIDDEN_IN_DOMAIN, imported_modules

SCREENING_ROOT = (
    Path(__file__).resolve().parents[2] / "src" / "ai_trading_analyst" / "domain" / "screening"
)


def _screening_modules() -> list[Path]:
    return sorted(SCREENING_ROOT.rglob("*.py"))


class TestScreeningDomainHatKeineInfrastrukturabhaengigkeit:
    @pytest.mark.parametrize("forbidden", FORBIDDEN_IN_DOMAIN)
    def test_signalkern_importiert_keine_infrastrukturbibliothek(self, forbidden: str) -> None:
        violations: list[str] = []
        for path in _screening_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for module_name in imported_modules(tree):
                if module_name.split(".")[0] == forbidden:
                    relative = path.relative_to(SCREENING_ROOT)
                    violations.append(f"{relative}: importiert {module_name}")

        assert not violations, (
            f"Der Signalkern darf nicht von '{forbidden}' abhaengen "
            f"(Sprint 1A, dedizierte Architekturvorgabe):\n" + "\n".join(violations)
        )

    def test_signalkern_importiert_keinen_konkreten_datenanbieter(self) -> None:
        """Der Signalkern kennt nur die eigenen Wertobjekte (Candle, CandleSeries,
        IndicatorValues) -- keinen Provider, keine Infrastructure-Schicht."""
        violations: list[str] = []
        for path in _screening_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for module_name in imported_modules(tree):
                if module_name.startswith("ai_trading_analyst.infrastructure"):
                    relative = path.relative_to(SCREENING_ROOT)
                    violations.append(f"{relative}: importiert {module_name}")

        assert not violations, (
            "Der Signalkern importiert Infrastructure-Code:\n" + "\n".join(violations)
        )

    def test_der_check_sieht_tatsaechlich_quelldateien(self) -> None:
        assert len(_screening_modules()) >= 3
