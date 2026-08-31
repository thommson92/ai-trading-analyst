"""Laden und Protokollieren der Konfiguration.

Doc 10, Paragraph 17 verlangt, dass Konfigurationsaenderungen protokolliert
werden. Deshalb liefert ``load_config`` neben der Konfiguration einen Fingerprint
des Dateiinhalts, der beim Anwendungsstart geloggt wird.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import SecretStr, ValidationError

from ai_trading_analyst.config.settings import AppConfig, Secrets
from ai_trading_analyst.observability.secret_redaction import register_secret

DEFAULT_CONFIG_ENV_VAR = "ATA_CONFIG_FILE"
_DEFAULT_CONFIG_FILENAME = "default.yaml"


class ConfigError(RuntimeError):
    """Die Konfiguration konnte nicht geladen oder nicht validiert werden."""


@dataclass(frozen=True, slots=True)
class LoadedConfig:
    """Konfiguration samt Herkunft -- beides wird beim Start protokolliert."""

    config: AppConfig
    source_path: Path
    fingerprint: str


def default_config_path() -> Path:
    """Pfad zu ``config/default.yaml`` im Projektwurzelverzeichnis.

    Die Reihenfolge ist bewusst: eine explizit gesetzte Umgebungsvariable
    gewinnt, damit Tests und abweichende Deployments nicht auf die Repo-Datei
    angewiesen sind.
    """
    override = os.environ.get(DEFAULT_CONFIG_ENV_VAR)
    if override:
        return Path(override)
    # loader.py -> config -> ai_trading_analyst -> src -> backend -> Projektwurzel
    project_root = Path(__file__).resolve().parents[4]
    return project_root / "config" / _DEFAULT_CONFIG_FILENAME


def load_config(path: Path | None = None) -> LoadedConfig:
    """Liest die YAML-Konfiguration und validiert sie gegen ``AppConfig``."""
    config_path = path if path is not None else default_config_path()

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"Konfigurationsdatei nicht lesbar: {config_path}") from error

    try:
        parsed: Any = yaml.safe_load(raw_text)
    except yaml.YAMLError as error:
        raise ConfigError(f"Konfigurationsdatei ist kein gueltiges YAML: {config_path}") from error

    # Eine Datei, die nur aus Kommentaren besteht, ergibt None -- das ist gueltig
    # und bedeutet "alle Defaults".
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ConfigError(
            f"Konfigurationsdatei muss ein Mapping enthalten, gefunden: "
            f"{type(parsed).__name__} ({config_path})"
        )

    try:
        config = AppConfig.model_validate(parsed)
    except ValidationError as error:
        raise ConfigError(f"Konfiguration ist ungueltig ({config_path}):\n{error}") from error

    fingerprint = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:16]
    return LoadedConfig(config=config, source_path=config_path, fingerprint=fingerprint)


def load_secrets() -> Secrets:
    """Liest die Geheimnisse aus den Umgebungsvariablen.

    Meldet dabei jeden gesetzten Wert bei der Schwaerzung an. Diese Funktion
    ist die einzige Stelle, an der der Betrieb Geheimnisse laedt -- CLI, API
    und Scheduler gehen alle durch sie hindurch. Der Schutz haengt damit
    nicht daran, dass ein einzelner Adapter daran denkt.
    """
    secrets = Secrets()
    for field_name in type(secrets).model_fields:
        value: SecretStr | None = getattr(secrets, field_name)
        if value is not None:
            register_secret(value.get_secret_value())
    return secrets
