from __future__ import annotations

from typing import Any

import pandas as pd

from services.google_sheets import carregar_aba


class FakeAPIError(Exception):
    pass


class FakeWorksheet:
    def __init__(self) -> None:
        self.calls = 0

    def get_all_records(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [{"Data": "2026-04-01", "Valor": 100}]


class FakeSpreadsheet:
    def __init__(self) -> None:
        self.calls = 0
        self.worksheet_obj = FakeWorksheet()

    def worksheet(self, nome_aba: str) -> FakeWorksheet:
        self.calls += 1
        if self.calls < 3:
            raise FakeAPIError("503 Service Unavailable")
        return self.worksheet_obj


def test_carregar_aba_retry_em_503_ao_buscar_worksheet(monkeypatch) -> None:
    monkeypatch.setattr("services.google_sheets.APIError", FakeAPIError)

    sleeps: list[float] = []
    monkeypatch.setattr("services.google_sheets.time.sleep", lambda value: sleeps.append(value))

    spreadsheet = FakeSpreadsheet()

    df = carregar_aba(spreadsheet, "FaturasPagas", ["Data", "Valor", "Extra"])

    assert spreadsheet.calls == 3
    assert sleeps == [1, 2]
    assert list(df.columns) == ["Data", "Valor", "Extra"]
    assert df.loc[0, "Valor"] == 100