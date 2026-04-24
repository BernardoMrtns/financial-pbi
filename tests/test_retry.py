from typing import List

import pytest

from utils.retry import retry_call


def test_retry_call_succeeds_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: List[float] = []
    monkeypatch.setattr("utils.retry.time.sleep", lambda value: sleeps.append(value))

    state = {"attempt": 0}

    def flaky() -> int:
        state["attempt"] += 1
        if state["attempt"] < 3:
            raise ValueError("temporary")
        return 42

    result = retry_call(
        flaky,
        retriable_exceptions=(ValueError,),
        operation_name="flaky operation",
        max_retries=4,
        base_delay_seconds=0.01,
    )

    assert result == 42
    assert state["attempt"] == 3
    assert sleeps == [0.01, 0.02]


def test_retry_call_raises_runtime_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("utils.retry.time.sleep", lambda _value: None)

    def always_fail() -> int:
        raise ConnectionError("network")

    with pytest.raises(RuntimeError, match="Falha em sync op apos 3 tentativas"):
        retry_call(
            always_fail,
            retriable_exceptions=(ConnectionError,),
            operation_name="sync op",
            max_retries=3,
            base_delay_seconds=0,
        )
