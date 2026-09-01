"""``/api/v1/reports`` -- der gespeicherte Analysebericht.

Das Dokument geht **unveraendert** hinaus, mit seinen deutschen Schluesseln
und allen achtzehn Abschnitten. Es ist die verbindliche Fassung (ADR 0039);
es beim Lesen umzubauen hiesse, einen abgeschlossenen Bericht durch heutigen
Code zu schicken (Doc 10, Paragraph 8).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ai_trading_analyst.domain.analysis import UnitOfWork

from ..dependencies import get_unit_of_work_factory

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/{report_id}")
def get_report(
    report_id: UUID,
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> dict[str, Any]:
    with uow_factory() as uow:
        report = uow.stock_reports.get(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bericht nicht gefunden."
        )
    return dict(report.document)
