# -*- coding: utf-8 -*-
import asyncio
import random
from typing import Callable, Optional, Set, TypeVar, Awaitable

from gpt.core.exceptions import LLMProviderError, is_retryable

T = TypeVar("T")


class RetryController:
    """集中式重試控制器：指數退避 + 抖動 + 上限，僅對可重試錯誤碼生效。"""

    def __init__(
        self,
        max_retries: int,
        base_delay: float,
        jitter: float,
        retryable_codes: Set[str],
        timeout_ceiling: Optional[float] = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.jitter = jitter
        self.retryable_codes = set(retryable_codes)
        self.timeout_ceiling = timeout_ceiling

    def _compute_delay(self, attempt: int) -> float:
        # attempt 從 1 起算：base * 2^(attempt-1)
        delay = self.base_delay * (2 ** (attempt - 1))
        delay *= (1.0 + random.uniform(0.0, self.jitter))
        if self.timeout_ceiling is not None:
            delay = min(delay, self.timeout_ceiling)
        return delay

    def _should_retry(self, err: Exception) -> Optional[str]:
        if isinstance(err, LLMProviderError):
            code = err.code
            if (code in self.retryable_codes) and is_retryable(code):
                return code
        return None

    async def run_async(
        self,
        fn: Callable[[], Awaitable[T]],
        on_try: Optional[Callable[[int], None]] = None,
        on_retry: Optional[Callable[[int, float, str], None]] = None,
    ) -> T:
        attempt = 0
        while True:
            attempt += 1
            if on_try:
                try:
                    on_try(attempt)
                except Exception:
                    # 打點回呼不應影響重試流程
                    pass
            try:
                return await fn()
            except Exception as e:
                code = self._should_retry(e)
                if code is None or attempt > self.max_retries:
                    # 不可重試或已達上限
                    raise
                delay = self._compute_delay(attempt)
                if on_retry:
                    try:
                        on_retry(attempt, delay, code)
                    except Exception:
                        pass
                await asyncio.sleep(delay)