"""Critical-path calculation (CPM) on a working calendar.

Pure functions: no database access, so they are easy to test. A task is a dict-like with
``id``, ``start_date`` and ``end_date`` (ISO text). Dependencies are (predecessor, successor, type, lag).

All arithmetic is done on *working-day indexes*: day 0 is the first working day of the calendar, day 1 the
next one, and so on. Weekends (per ``work_days``) and holidays are skipped.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

DEP_TYPES = ("FS", "SS", "FF", "SF")
DEFAULT_WORK_DAYS = (0, 1, 2, 3, 4, 5)          # Monday-Saturday (date.weekday())


class CycleError(ValueError):
    """The dependencies form a loop."""


def parse_work_days(text: str | None) -> tuple[int, ...]:
    days = sorted({int(p) for p in (text or "").split(",") if p.strip().isdigit() and 0 <= int(p) <= 6})
    return tuple(days) or DEFAULT_WORK_DAYS


class WorkCalendar:
    def __init__(self, first: date, last: date, work_days: Iterable[int] = DEFAULT_WORK_DAYS,
                 holidays: Iterable[str] = ()):
        self.work_days = set(work_days) or set(DEFAULT_WORK_DAYS)
        off = set(holidays)
        self.days: list[date] = []
        d = first
        while d <= last:
            if d.weekday() in self.work_days and d.isoformat() not in off:
                self.days.append(d)
            d += timedelta(days=1)
        if not self.days:
            self.days.append(first)

    def next_idx(self, d: date) -> int:
        """Index of the first working day on or after d (clamped to the calendar)."""
        return min(bisect_left(self.days, d), len(self.days) - 1)

    def prev_idx(self, d: date) -> int:
        """Index of the last working day on or before d (clamped to the calendar)."""
        return max(bisect_right(self.days, d) - 1, 0)

    def date_of(self, idx: int) -> date:
        return self.days[max(0, min(idx, len(self.days) - 1))]

    def count(self, a: date, b: date) -> int:
        """Working days between a and b inclusive (0 when b is before a)."""
        if b < a:
            return 0
        return max(0, self.prev_idx(b) - self.next_idx(a) + 1)


@dataclass
class Scheduled:
    task_id: int
    duration: int                  # working days
    es: date
    ef: date
    ls: date
    lf: date
    total_float: int               # working days
    critical: bool
    shift: int                     # working days the early start moved later than the task's own planned start


def _topo(ids: list[int], edges: list[tuple[int, int]]) -> list[int]:
    succ: dict[int, list[int]] = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for p, s in edges:
        succ[p].append(s)
        indeg[s] += 1
    order = [i for i in ids if indeg[i] == 0]
    for node in order:
        for nxt in succ[node]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                order.append(nxt)
    if len(order) != len(ids):
        raise CycleError("Các phụ thuộc tạo thành vòng lặp.")
    return order


def would_cycle(edges: list[tuple[int, int]], predecessor: int, successor: int) -> bool:
    """True when adding predecessor -> successor to ``edges`` would create a loop."""
    if predecessor == successor:
        return True
    graph: dict[int, list[int]] = {}
    for p, s in edges:
        graph.setdefault(p, []).append(s)
    stack, seen = [successor], set()
    while stack:
        node = stack.pop()
        if node == predecessor:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, []))
    return False


def compute(tasks: list[dict], deps: list[tuple[int, int, str, int]], calendar: WorkCalendar) -> dict[int, Scheduled]:
    """Forward and backward pass. Tasks without both dates are left out."""
    data: dict[int, tuple[int, int]] = {}                       # id -> (own start idx, duration)
    for t in tasks:
        try:
            s, e = date.fromisoformat(t["start_date"]), date.fromisoformat(t["end_date"])
        except (TypeError, ValueError, KeyError):
            continue
        si = calendar.next_idx(s)
        data[t["id"]] = (si, max(1, calendar.prev_idx(e) - si + 1))
    ids = list(data)
    rel = [(p, s, ty if ty in DEP_TYPES else "FS", int(lag or 0)) for p, s, ty, lag in deps
           if p in data and s in data and p != s]
    order = _topo(ids, [(p, s) for p, s, _, _ in rel])

    into: dict[int, list] = {i: [] for i in ids}
    out: dict[int, list] = {i: [] for i in ids}
    for r in rel:
        into[r[1]].append(r)
        out[r[0]].append(r)

    es: dict[int, int] = {}
    ef: dict[int, int] = {}
    for i in order:
        own_start, dur = data[i]
        start = own_start
        for p, _, ty, lag in into[i]:
            if ty == "FS":
                start = max(start, ef[p] + 1 + lag)
            elif ty == "SS":
                start = max(start, es[p] + lag)
            elif ty == "FF":
                start = max(start, ef[p] + lag - dur + 1)
            else:  # SF
                start = max(start, es[p] + lag - dur + 1)
        es[i], ef[i] = start, start + dur - 1

    finish = max(ef.values(), default=0)
    ls: dict[int, int] = {}
    lf: dict[int, int] = {}
    for i in reversed(order):
        dur = data[i][1]
        latest_finish = finish
        for _, s, ty, lag in out[i]:
            if ty == "FS":
                latest_finish = min(latest_finish, ls[s] - 1 - lag)
            elif ty == "SS":
                latest_finish = min(latest_finish, ls[s] - lag + dur - 1)
            elif ty == "FF":
                latest_finish = min(latest_finish, lf[s] - lag)
            else:  # SF
                latest_finish = min(latest_finish, lf[s] - lag + dur - 1)
        lf[i], ls[i] = latest_finish, latest_finish - dur + 1

    result: dict[int, Scheduled] = {}
    for i in ids:
        slack = ls[i] - es[i]
        result[i] = Scheduled(
            task_id=i, duration=data[i][1], es=calendar.date_of(es[i]), ef=calendar.date_of(ef[i]),
            ls=calendar.date_of(ls[i]), lf=calendar.date_of(lf[i]), total_float=slack, critical=slack <= 0,
            shift=es[i] - data[i][0])
    return result


def project_finish(result: dict[int, Scheduled]) -> date | None:
    return max((s.ef for s in result.values()), default=None)
