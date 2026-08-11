import json
from pathlib import Path

from ibkrspike.results_store import save_result


def test_save_result_schreibt_redigierte_json_datei(tmp_path: Path) -> None:
    path = save_result(
        "connectivity",
        {"_status": "ok", "managed_accounts": ["U1234567"]},
        results_dir=tmp_path,
    )

    assert path.exists()
    assert path.parent == tmp_path
    assert "connectivity" in path.name

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["_status"] == "ok"
    assert written["managed_accounts"] == ["U*****67"]
