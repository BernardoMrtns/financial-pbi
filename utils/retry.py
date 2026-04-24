import time
from typing import Any, Callable, Tuple, Type

from config import MAX_RETRIES, RETRY_BASE_DELAY_SECONDS


def retry_call(
    func: Callable[[], Any],
    retriable_exceptions: Tuple[Type[BaseException], ...],
    operation_name: str,
    max_retries: int = MAX_RETRIES,
    base_delay_seconds: float = RETRY_BASE_DELAY_SECONDS,
) -> Any:
    last_error: BaseException | None = None

    for attempt in range(max_retries):
        try:
            return func()
        except retriable_exceptions as error:
            last_error = error
            if attempt == max_retries - 1:
                break
            time.sleep(base_delay_seconds * (2 ** attempt))

    if last_error is not None:
        raise RuntimeError(f"Falha em {operation_name} apos {max_retries} tentativas") from last_error

    raise RuntimeError(f"Falha inesperada em {operation_name}")
