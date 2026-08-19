"""Subprocess-isolated capture-datetime extraction.

organizer.metadata.get_capture_datetime() is hardened against every
Python-level exception, but it can't protect against a native crash
(segfault / heap corruption) inside the C extensions it calls into --
Pillow, pillow-heif, exifread, hachoir -- when handed a malformed or
unusual real-world file. A native crash on the scanning thread takes
the whole process down with it.

This module runs that extraction in worker subprocesses instead, so a
native crash only kills the one worker that hit the bad file. The
crashed file is reported back as an error (see resolve_capture_datetimes)
and the rest of the scan continues.
"""
from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from organizer import metadata
from organizer.models import FileCategory, ScanError

# Batch size trades per-task IPC/pickling overhead against crash blast
# radius: a larger batch amortizes the round-trip cost across more
# files (important for source trees with tens of thousands of files),
# but if a worker dies mid-batch every file in that batch needs to be
# retried/bisected before the scan can be sure which one was at fault.
_BATCH_SIZE = 20

# forkserver is requested explicitly rather than relying on whatever
# this platform's default happens to be: plain fork() is documented as
# unsafe to combine with a multi-threaded parent process, and this pool
# is created from ScanWorker's QThread alongside the Qt GUI thread.
# forkserver pays its one-time bootstrap cost once (the first pool
# created in a process), then forks fresh workers from that clean,
# single-threaded helper for every submit()/restart() after.
_MP_CONTEXT = multiprocessing.get_context("forkserver")

MediaItem = tuple[Path, FileCategory]
MetadataResult = tuple  # (datetime, str) -- see organizer.metadata.get_capture_datetime


def _extract_batch(items: list[MediaItem]) -> list[MetadataResult]:
    """Runs inside a worker subprocess. Must be a top-level function so
    it's picklable. get_capture_datetime() already never raises a
    Python exception -- the only failure mode left is a native crash,
    which kills this worker process instead, which is exactly what
    resolve_capture_datetimes() below is built to detect and recover
    from."""
    return [metadata.get_capture_datetime(path, category) for path, category in items]


class _WorkerPool:
    """Owns one ProcessPoolExecutor, recreatable after a worker crash."""

    def __init__(self, max_workers: int | None = None, worker_fn=_extract_batch) -> None:
        self.max_workers = max_workers or os.cpu_count() or 1
        # worker_fn is only ever overridden by tests, to exercise a real
        # worker-process crash without needing to actually corrupt a
        # file badly enough to crash Pillow/hachoir. It must stay a
        # top-level, picklable callable -- see _extract_batch's docstring.
        self._worker_fn = worker_fn
        self._executor = self._new_executor()

    def _new_executor(self) -> ProcessPoolExecutor:
        return ProcessPoolExecutor(max_workers=self.max_workers, mp_context=_MP_CONTEXT)

    def submit_batch(self, batch: list[MediaItem]) -> Future:
        return self._executor.submit(self._worker_fn, batch)

    def restart(self) -> None:
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self._executor = self._new_executor()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)


def _recover_batch(
    pool: _WorkerPool,
    batch: list[MediaItem],
    results: dict[Path, MetadataResult],
    errors: list[ScanError],
    on_item_resolved,
) -> None:
    """Called when a batch's future raised BrokenProcessPool.

    When one worker dies, CPython's ProcessPoolExecutor marks *every*
    pending work item BrokenProcessPool and terminates every other
    worker too -- not just the batch that actually caused the crash.
    So this first retries the whole batch once on a freshly restarted
    pool, to rule out this batch being innocent collateral damage from
    a different batch's crash. Only if it fails again does it bisect
    down to one file at a time, so exactly the poison file is blamed
    while its batch-mates still succeed.
    """
    if len(batch) > 1:
        try:
            for (path, _category), result in zip(batch, pool.submit_batch(batch).result()):
                results[path] = result
                if on_item_resolved is not None:
                    on_item_resolved()
            return
        except BrokenProcessPool:
            pool.restart()

    for path, category in batch:
        try:
            result = pool.submit_batch([(path, category)]).result()[0]
            results[path] = result
        except BrokenProcessPool:
            pool.restart()
            errors.append(ScanError(
                source_path=path,
                stage="metadata",
                message="Parser crashed (native error) while reading metadata; file skipped",
            ))
        finally:
            if on_item_resolved is not None:
                on_item_resolved()


def resolve_capture_datetimes(
    media_items: list[MediaItem],
    on_item_resolved=None,
    batch_size: int = _BATCH_SIZE,
    max_workers: int | None = None,
    _worker_fn=_extract_batch,
) -> tuple[dict[Path, MetadataResult], list[ScanError]]:
    """Resolve a capture datetime for every (path, category) in media_items.

    Every item ends up in exactly one of the two return values: the
    results dict on success, or the errors list if extracting its
    metadata crashed the worker parsing it. `on_item_resolved` (if
    given) is called exactly once per item, success or failure, so
    callers can drive a progress counter without caring which case it
    was.

    `_worker_fn` is a test-only seam (see _WorkerPool) -- production
    callers should never pass it.
    """
    if not media_items:
        return {}, []

    results: dict[Path, MetadataResult] = {}
    errors: list[ScanError] = []
    pending = [media_items[i:i + batch_size] for i in range(0, len(media_items), batch_size)]

    pool = _WorkerPool(max_workers=max_workers, worker_fn=_worker_fn)
    try:
        in_flight: dict[Future, list[MediaItem]] = {}

        def _fill_window() -> None:
            while pending and len(in_flight) < pool.max_workers:
                batch = pending.pop(0)
                in_flight[pool.submit_batch(batch)] = batch

        _fill_window()
        while in_flight:
            done, _ = wait(list(in_flight.keys()), return_when=FIRST_COMPLETED)
            for fut in done:
                batch = in_flight.pop(fut)
                try:
                    for (path, _category), result in zip(batch, fut.result()):
                        results[path] = result
                        if on_item_resolved is not None:
                            on_item_resolved()
                except BrokenProcessPool:
                    pool.restart()
                    _recover_batch(pool, batch, results, errors, on_item_resolved)
            _fill_window()
    finally:
        pool.shutdown()

    return results, errors
