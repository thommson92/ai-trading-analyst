from __future__ import annotations

from tvcdp.diagnostics import EnvironmentInfo


class TestEnvironmentInfo:
    def test_collect_liefert_alle_felder_nicht_leer(self) -> None:
        info = EnvironmentInfo.collect()

        assert info.operating_system
        assert info.python_version
        assert info.hostname
        assert info.collected_at

    def test_is_windows_und_is_macos_sind_exklusiv_fuer_bekannte_systeme(self) -> None:
        macos_info = EnvironmentInfo(
            operating_system="Darwin",
            os_version="23.0",
            architecture="arm64",
            python_version="3.12.0",
            hostname="test",
            collected_at="2026-01-01T00:00:00+00:00",
        )
        assert macos_info.is_macos is True
        assert macos_info.is_windows is False

        windows_info = EnvironmentInfo(
            operating_system="Windows",
            os_version="10.0.19045",
            architecture="AMD64",
            python_version="3.12.0",
            hostname="test",
            collected_at="2026-01-01T00:00:00+00:00",
        )
        assert windows_info.is_windows is True
        assert windows_info.is_macos is False
