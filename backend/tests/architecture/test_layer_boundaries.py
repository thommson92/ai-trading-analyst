"""Setzt die Schichtgrenzen aus Doc 10, Paragraph 9 automatisiert durch.

Die wichtigste Regel des Projekts lautet: Der Domain Layer darf nicht von
FastAPI, SQLAlchemy, TradingView oder einem konkreten KI-Anbieter abhaengen.
Eine Regel, die nur in einem Dokument steht, wird im Alltag verletzt -- dieser
Test macht daraus einen Build-Fehler.

Geprueft wird der Import-Graph statisch ueber den AST, ohne die Module zu
importieren. So schlaegt der Test auch dann an, wenn ein verbotener Import in
einem Zweig steht, der zur Laufzeit selten erreicht wird.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "ai_trading_analyst"
PACKAGE_NAME = "ai_trading_analyst"

# Welche Schicht darf welche anderen Schichten importieren.
ALLOWED_LAYER_IMPORTS: dict[str, frozenset[str]] = {
    "domain": frozenset(),
    "application": frozenset({"domain"}),
    "infrastructure": frozenset({"domain"}),
    "presentation": frozenset({"domain", "application"}),
}

# Querschnittspakete, die jede Schicht nutzen darf.
SHARED_PACKAGES = frozenset({"config", "observability"})

# Technologien, die im Domain Layer nichts zu suchen haben (Doc 10, Paragraph 9).
FORBIDDEN_IN_DOMAIN = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "httpx",
    "requests",
    "anthropic",
    "openai",
    "redis",
    "yaml",
    "uvicorn",
)


def iter_modules() -> Iterator[tuple[Path, ast.Module]]:
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_modules(tree: ast.Module) -> Iterator[str]:
    """Alle importierten Modulnamen, unabhaengig von der Importform."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            # Relative Importe (level > 0) bleiben innerhalb des eigenen Pakets
            # und koennen die Schichtgrenze nicht verletzen.
            if node.level == 0 and node.module is not None:
                yield node.module


def layer_of(path: Path) -> str | None:
    relative = path.relative_to(PACKAGE_ROOT)
    top_level = relative.parts[0]
    return top_level if top_level in ALLOWED_LAYER_IMPORTS else None


def internal_layer_of(module_name: str) -> str | None:
    if not module_name.startswith(f"{PACKAGE_NAME}."):
        return None
    return module_name.split(".")[1]


class TestLayerBoundaries:
    def test_layers_only_import_what_they_are_allowed_to(self) -> None:
        violations: list[str] = []

        for path, tree in iter_modules():
            source_layer = layer_of(path)
            if source_layer is None:
                continue

            allowed = ALLOWED_LAYER_IMPORTS[source_layer] | SHARED_PACKAGES
            for module_name in imported_modules(tree):
                target_layer = internal_layer_of(module_name)
                if target_layer is None or target_layer == source_layer:
                    continue
                if target_layer not in allowed:
                    violations.append(
                        f"{path.relative_to(PACKAGE_ROOT)}: '{source_layer}' importiert "
                        f"'{target_layer}' ({module_name})"
                    )

        assert not violations, "Verletzte Schichtgrenzen:\n" + "\n".join(violations)

    @pytest.mark.parametrize("forbidden", FORBIDDEN_IN_DOMAIN)
    def test_domain_layer_is_free_of_infrastructure_libraries(self, forbidden: str) -> None:
        domain_root = PACKAGE_ROOT / "domain"
        violations: list[str] = []

        for path in sorted(domain_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for module_name in imported_modules(tree):
                root_package = module_name.split(".")[0]
                if root_package == forbidden:
                    violations.append(f"{path.relative_to(PACKAGE_ROOT)}: importiert {module_name}")

        assert not violations, (
            f"Der Domain Layer darf nicht von '{forbidden}' abhaengen "
            f"(Doc 10, Paragraph 9):\n" + "\n".join(violations)
        )

    def test_every_layer_package_exists(self) -> None:
        """Schuetzt den Test davor, durch eine Umbenennung wirkungslos zu werden."""
        for layer in ALLOWED_LAYER_IMPORTS:
            assert (PACKAGE_ROOT / layer / "__init__.py").is_file(), f"Fehlende Schicht: {layer}"

    def test_the_check_actually_sees_source_files(self) -> None:
        """Ein leerer Import-Graph wuerde jeden Verstoss uebersehen."""
        assert sum(1 for _ in iter_modules()) >= 8


class TestDetectionItself:
    """Der Waechter braucht selbst einen Waechter."""

    def test_forbidden_import_would_be_detected(self, tmp_path: Path) -> None:
        module = tmp_path / "beispiel.py"
        module.write_text("import sqlalchemy\nfrom fastapi import APIRouter\n", encoding="utf-8")
        tree = ast.parse(module.read_text(encoding="utf-8"))

        found = {name.split(".")[0] for name in imported_modules(tree)}

        assert {"sqlalchemy", "fastapi"} <= found

    def test_cross_layer_import_would_be_detected(self, tmp_path: Path) -> None:
        module = tmp_path / "beispiel.py"
        module.write_text(
            f"from {PACKAGE_NAME}.infrastructure.db import Session\n", encoding="utf-8"
        )
        tree = ast.parse(module.read_text(encoding="utf-8"))

        layers = {internal_layer_of(name) for name in imported_modules(tree)}

        assert "infrastructure" in layers

    def test_a_layer_importing_the_composition_root_would_be_detected(self) -> None:
        """``bootstrap.py`` liegt bewusst ausserhalb der vier Schichten und darf
        als einziger Ort alle Schichten gleichzeitig verdrahten (Composition
        Root, Sprint 1B). Der Rueckweg -- eine Schicht importiert bootstrap.py
        zurueck -- ist nicht gesondert verboten, sondern faellt automatisch
        unter die bestehende Regel: 'bootstrap' ist kein bekannter Layer- und
        kein Shared-Package-Name, jeder Import daraus aus einer Schicht heraus
        ist deshalb bereits ein target_layer, der nicht in ``allowed`` steht."""
        allowed_for_presentation = ALLOWED_LAYER_IMPORTS["presentation"] | SHARED_PACKAGES

        assert "bootstrap" not in allowed_for_presentation
        assert "bootstrap" not in ALLOWED_LAYER_IMPORTS
