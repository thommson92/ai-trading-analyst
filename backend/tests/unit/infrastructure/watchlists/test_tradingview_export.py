"""Einlesen der exportierten Watchlisten.

Die Beispiele stammen wortwoertlich aus den drei Dateien des Nutzers, damit
der Test die tatsaechliche Exportform trifft und nicht eine angenommene.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_trading_analyst.infrastructure.ibkr import ContractSpec
from ai_trading_analyst.infrastructure.watchlists.tradingview_export import (
    WatchlistError,
    deduplicate,
    describe_sources,
    load_watchlist_directory,
    parse_watchlist,
)

MARKET_CAP = "NASDAQ:NVDA,NASDAQ:AAPL,NYSE:BRK.B,NASDAQ:MU"
MIT_ABSCHNITTEN = "###PJM SONSTIGE,NYSE:ABT,NASDAQ:ADSK,###VALUE LINE,NYSE:A,NASDAQ:CDNS"


class TestParseWatchlist:
    def test_boerse_und_symbol_werden_getrennt(self) -> None:
        contracts = parse_watchlist("NASDAQ:NVDA")
        assert contracts == (ContractSpec(symbol="NVDA", primary_exchange="NASDAQ"),)

    def test_die_boerse_wird_zur_heimatboerse_nicht_zum_handelsweg(self) -> None:
        contract = parse_watchlist("NYSE:JPM")[0]
        assert contract.primary_exchange == "NYSE"
        assert contract.exchange == "SMART"
        assert contract.currency == "USD"

    def test_anteilsklassen_werden_in_die_ibkr_schreibweise_uebersetzt(self) -> None:
        # TradingView schreibt BRK.B, IBKR erwartet BRK B.
        assert parse_watchlist("NYSE:BRK.B")[0].symbol == "BRK B"

    def test_abschnittsueberschriften_sind_keine_symbole(self) -> None:
        symbols = [contract.symbol for contract in parse_watchlist(MIT_ABSCHNITTEN)]
        assert symbols == ["ABT", "ADSK", "A", "CDNS"]

    def test_ein_symbol_ohne_boerse_bleibt_ohne_heimatboerse(self) -> None:
        contract = parse_watchlist("AAPL")[0]
        assert contract.symbol == "AAPL"
        assert contract.primary_exchange is None

    def test_eine_unbekannte_boerse_wird_abgelehnt_statt_ignoriert(self) -> None:
        # Wegzulassen waere gefaehrlich: SAP wuerde dann als US-Papier ueber
        # SMART/USD angefragt, und IBKR loeste womoeglich das ADR auf.
        with pytest.raises(WatchlistError, match="XETR"):
            parse_watchlist("XETR:SAP")

    def test_zeilenumbrueche_und_leerraum_stoeren_nicht(self) -> None:
        symbols = [contract.symbol for contract in parse_watchlist("NASDAQ:NVDA,\n NYSE:JPM ,\n")]
        assert symbols == ["NVDA", "JPM"]

    def test_die_reihenfolge_der_datei_bleibt_erhalten(self) -> None:
        symbols = [contract.symbol for contract in parse_watchlist(MARKET_CAP)]
        assert symbols == ["NVDA", "AAPL", "BRK B", "MU"]


class TestDeduplicate:
    def test_dasselbe_symbol_aus_zwei_listen_wird_einmal_gefuehrt(self) -> None:
        contracts = deduplicate(
            [
                ContractSpec(symbol="MU", primary_exchange="NASDAQ"),
                ContractSpec(symbol="NVDA", primary_exchange="NASDAQ"),
                ContractSpec(symbol="MU", primary_exchange="NASDAQ"),
            ]
        )
        assert [contract.symbol for contract in contracts] == ["MU", "NVDA"]

    def test_das_erste_vorkommen_gewinnt(self) -> None:
        contracts = deduplicate(
            [
                ContractSpec(symbol="MU", primary_exchange="NASDAQ"),
                ContractSpec(symbol="MU", primary_exchange=None),
            ]
        )
        assert contracts[0].primary_exchange == "NASDAQ"


class TestLoadWatchlistDirectory:
    def test_alle_dateien_werden_zusammengefasst(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("NASDAQ:NVDA,NASDAQ:MU", encoding="utf-8")
        (tmp_path / "b.txt").write_text("NYSE:JPM,NASDAQ:MU", encoding="utf-8")
        symbols = [contract.symbol for contract in load_watchlist_directory(tmp_path)]
        assert symbols == ["NVDA", "MU", "JPM"]

    def test_dateien_ohne_txt_endung_werden_ignoriert(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("NASDAQ:NVDA", encoding="utf-8")
        (tmp_path / "notizen.md").write_text("NYSE:JPM", encoding="utf-8")
        assert [contract.symbol for contract in load_watchlist_directory(tmp_path)] == ["NVDA"]

    def test_eine_datei_mit_byte_order_mark_wird_gelesen(self, tmp_path: Path) -> None:
        # Der Windows-Editor schreibt gern ein BOM an den Dateianfang.
        (tmp_path / "a.txt").write_text("NASDAQ:NVDA", encoding="utf-8-sig")
        assert [contract.symbol for contract in load_watchlist_directory(tmp_path)] == ["NVDA"]

    def test_fehlendes_verzeichnis_scheitert_eindeutig(self, tmp_path: Path) -> None:
        with pytest.raises(WatchlistError, match="existiert nicht"):
            load_watchlist_directory(tmp_path / "gibtsnicht")

    def test_verzeichnis_ohne_watchlist_datei_scheitert(self, tmp_path: Path) -> None:
        (tmp_path / "notizen.md").write_text("egal", encoding="utf-8")
        with pytest.raises(WatchlistError, match=r"keine \.txt-Datei"):
            load_watchlist_directory(tmp_path)

    def test_dateien_ganz_ohne_symbole_scheitern(self, tmp_path: Path) -> None:
        # Sonst laeuft ein Screening ueber null Aktien durch und sieht wie ein
        # erfolgreicher Lauf aus.
        (tmp_path / "a.txt").write_text("###NUR EINE UEBERSCHRIFT", encoding="utf-8")
        with pytest.raises(WatchlistError, match="kein einziges Symbol"):
            load_watchlist_directory(tmp_path)

    def test_die_endung_wird_unabhaengig_von_der_schreibweise_erkannt(self, tmp_path: Path) -> None:
        # Der Windows-Explorer speichert Textdateien gelegentlich als .TXT.
        (tmp_path / "a.TXT").write_text("NASDAQ:NVDA", encoding="utf-8")
        assert [contract.symbol for contract in load_watchlist_directory(tmp_path)] == ["NVDA"]
        assert describe_sources(tmp_path) == ("a.TXT",)

    def test_die_quellen_werden_benannt(self, tmp_path: Path) -> None:
        (tmp_path / "b.txt").write_text("NYSE:JPM", encoding="utf-8")
        (tmp_path / "a.txt").write_text("NASDAQ:NVDA", encoding="utf-8")
        assert describe_sources(tmp_path) == ("a.txt", "b.txt")


class TestEchteWatchlisten:
    """Gegen die tatsaechlich hinterlegten Dateien des Projekts.

    Faengt Formatabweichungen ab, die ein selbst geschriebenes Beispiel nicht
    haette -- der Test ueberspringt sich, wenn das Verzeichnis fehlt.
    """

    @staticmethod
    def _directory() -> Path:
        return Path(__file__).resolve().parents[5] / "watchlists"

    def test_die_hinterlegten_listen_ergeben_eine_plausible_watchlist(self) -> None:
        directory = self._directory()
        if not directory.is_dir():
            pytest.skip(f"Kein Watchlist-Verzeichnis unter {directory}")

        contracts = load_watchlist_directory(directory)
        assert len(contracts) > 100
        assert len({contract.symbol for contract in contracts}) == len(contracts)
        assert all(contract.symbol.strip() == contract.symbol for contract in contracts)
        assert all("." not in contract.symbol for contract in contracts)
        assert all(not contract.symbol.startswith("#") for contract in contracts)
