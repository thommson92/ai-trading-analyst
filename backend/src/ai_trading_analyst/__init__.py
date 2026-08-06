"""AI Trading Analyst.

Die Anwendung ist in vier Schichten geteilt (Doc 10, Paragraph 9):

``domain``
    Fachliche Regeln und Provider-Schnittstellen. Haengt von keiner
    Infrastruktur ab -- kein FastAPI, kein SQLAlchemy, kein Datenanbieter,
    kein KI-Anbieter. Die Architekturtests setzen das durch.
``application``
    Use Cases, Orchestrierung, Transaktionsgrenzen, Berechtigungen.
``infrastructure``
    Repositories und Adapter fuer Datenbank, Marktdaten, KI und Push.
``presentation``
    FastAPI-Endpunkte und Schemas.
"""

__version__ = "0.1.0"
