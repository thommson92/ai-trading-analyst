"""Entfernt sensible Daten aus allem, was geloggt oder als Ergebnisdatei
persistiert wird.

Der Spike hat ausdruecklich das Ziel *nachzuweisen*, ob eine bestehende
authentifizierte TradingView-Sitzung genutzt werden kann -- er darf dabei
aber nie Session-Cookies, Tokens oder sonstige Zugangsdaten selbst
einsammeln oder speichern (Vorgabe: "Keine Zugangsdaten, Session-Cookies,
Tokens oder sonstigen Secrets duerfen im Repository, in Fixtures,
Screenshots oder Logs landen").

Zwei Verteidigungslinien:

1. Die Extraktions-Schritte fragen von sich aus nur nach booleschen oder
   strukturellen Signalen (siehe ``steps/step_session_check.py``), nie nach
   Cookie- oder Storage-Inhalten.
2. Diese Redaction-Schicht ist eine zweite, unabhaengige Absicherung: jeder
   Wert, der dennoch in ein Ergebnis-Dict oder eine Logzeile gerueten sollte,
   wird hier vor der Persistierung nochmals gefiltert.
"""

from __future__ import annotations

import re
from typing import Any

_REDACTED = "***REDACTED***"

# Schluesselnamen, deren Werte pauschal entfernt werden, unabhaengig vom Inhalt.
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(cookie|token|secret|password|passwd|api[_-]?key|auth|session[_-]?id|"
    r"bearer|credential|set-cookie)",
    re.IGNORECASE,
)

# Werte, die wie ein Zugangsdaten-Artefakt aussehen, auch wenn der
# Schluesselname unauffaellig ist (z. B. eine rohe JWT- oder Bearer-Zeichenkette
# in einer Fehlermeldung).
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9\-_.]+\b", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b"),  # JWT
    re.compile(r"(?i)\bsessionid=[^;&\s]+"),
)


def _redact_string(value: str) -> str:
    redacted = value
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted


def redact(value: Any) -> Any:
    """Entfernt rekursiv sensible Schluessel/Werte aus JSON-aehnlichen Strukturen.

    Sicherheitsprinzip: im Zweifel redigieren. Ein zu aggressiv entfernter,
    harmloser Wert im Spike-Bericht ist ein akzeptabler Preis; ein
    durchgerutschtes Secret ist es nicht.
    """
    if isinstance(value, dict):
        return {
            key: (
                _REDACTED
                if _SENSITIVE_KEY_PATTERN.search(str(key))
                and not isinstance(val, dict | list | tuple)
                else redact(val)
            )
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value
