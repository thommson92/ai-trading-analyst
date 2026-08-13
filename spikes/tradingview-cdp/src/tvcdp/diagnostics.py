"""Umgebungserkennung -- bewusst nur mit der Python-Standardbibliothek.

Kernanforderung des Spikes: keine Windows-Annahmen fest im Kern verdrahten.
Dieses Modul liest die tatsaechliche Plattform zur Laufzeit aus, statt sie
anzunehmen, und liefert dieselbe Struktur unter macOS wie unter Windows.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class EnvironmentInfo:
    operating_system: str
    os_version: str
    architecture: str
    python_version: str
    hostname: str
    collected_at: str

    @classmethod
    def collect(cls) -> EnvironmentInfo:
        return cls(
            operating_system=platform.system(),
            os_version=platform.version(),
            architecture=platform.machine(),
            python_version=sys.version.split()[0],
            hostname=platform.node(),
            collected_at=datetime.now(UTC).isoformat(),
        )

    @property
    def is_windows(self) -> bool:
        return self.operating_system.lower() == "windows"

    @property
    def is_macos(self) -> bool:
        return self.operating_system.lower() == "darwin"
