from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True)
class ReplaySchedulerConfig:
    concurrency: int = 1

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            raise ValueError("replay scheduler concurrency must be >= 1")


@dataclass(frozen=True)
class ReplayJobResult:
    index: int
    ok: bool
    result: object | None = None
    error: str | None = None


def run_replay_jobs(
    jobs: Iterable[T],
    worker: Callable[[T], R],
    *,
    config: ReplaySchedulerConfig | None = None,
) -> list[ReplayJobResult]:
    cfg = config or ReplaySchedulerConfig()
    indexed = list(enumerate(jobs))
    if cfg.concurrency == 1:
        results: list[ReplayJobResult] = []
        for index, job in indexed:
            try:
                results.append(ReplayJobResult(index=index, ok=True, result=worker(job)))
            except Exception as exc:
                results.append(ReplayJobResult(index=index, ok=False, error=f"{type(exc).__name__}: {exc}"))
        return results

    results_by_index: dict[int, ReplayJobResult] = {}
    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        futures = {pool.submit(worker, job): index for index, job in indexed}
        for future in as_completed(futures):
            index = futures[future]
            try:
                results_by_index[index] = ReplayJobResult(index=index, ok=True, result=future.result())
            except Exception as exc:
                results_by_index[index] = ReplayJobResult(index=index, ok=False, error=f"{type(exc).__name__}: {exc}")
    return [results_by_index[index] for index, _job in indexed]
