"""What the home page shows: one card per project the user may open, with search, filters and director KPIs."""
from __future__ import annotations

import unicodedata
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from .. import repositories as repo
from ..models import Project, User

STATUS_LABELS = {"dang_thi_cong": "Đang thi công", "tam_dung": "Tạm dừng", "hoan_thanh": "Hoàn thành"}
SORTS = {"recent": "Mới nhất", "name": "Tên A–Z", "progress": "Tiến độ cao nhất", "end": "Sắp đến hạn"}
SEARCH_FIELDS = ("name", "slug", "client", "contractor", "package_name")


def fold(text: str | None) -> str:
    """Lower case, no accents, so “nha may” finds “Nhà máy” and “dong a” finds “Đông Á”."""
    text = unicodedata.normalize("NFKD", (text or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def _days_between(start: str, end: str) -> int | None:
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (TypeError, ValueError):
        return None


def build_card(project: Project, today: str, progress: dict[int, float], overdue: dict[int, int]) -> dict[str, Any]:
    status = project.construction_status if project.construction_status in STATUS_LABELS else "dang_thi_cong"
    days_left = _days_between(today, project.end_date) if project.end_date else None
    late = status != "hoan_thanh" and days_left is not None and days_left < 0
    return {"id": project.id, "name": project.name, "slug": project.slug, "client": project.client or "",
            "contractor": project.contractor or "", "package_name": project.package_name or "",
            "status": status, "status_label": STATUS_LABELS[status], "progress": progress.get(project.id),
            "start_date": project.start_date, "end_date": project.end_date, "days_left": days_left,
            "late": late, "overdue_tasks": overdue.get(project.id, 0),
            "year": (project.start_date or project.created_at or "")[:4]}


def all_cards(db: Session, user: User | None, today: str) -> list[dict[str, Any]]:
    progress = repo.progress_by_project(db)
    overdue = repo.overdue_tasks_by_project(db, today)
    return [build_card(p, today, progress, overdue) for p in repo.list_projects(db, user=user)]


def _matches(card: dict[str, Any], tokens: list[str]) -> bool:
    haystack = fold(" ".join(str(card.get(field) or "") for field in SEARCH_FIELDS))
    return all(token in haystack for token in tokens)


def _sort_key(sort: str):
    if sort == "name":
        return lambda c: fold(c["name"])
    if sort == "progress":
        return lambda c: -(c["progress"] if c["progress"] is not None else -1)
    if sort == "end":
        return lambda c: (c["end_date"] is None, c["end_date"] or "")
    return lambda c: -c["id"]


def filter_cards(cards: list[dict[str, Any]], q: str = "", status: str = "", year: str = "",
                 sort: str = "recent") -> list[dict[str, Any]]:
    tokens = [t for t in fold(q).split() if t]
    result = [c for c in cards
              if (not tokens or _matches(c, tokens)) and (not status or c["status"] == status)
              and (not year or c["year"] == year)]
    return sorted(result, key=_sort_key(sort if sort in SORTS else "recent"))


def kpis(db: Session, cards: list[dict[str, Any]]) -> dict[str, Any]:
    ids = {c["id"] for c in cards}
    costs = repo.cost_sums_by_project(db)
    risks = repo.open_high_risks_by_project(db)
    return {"projects": len(cards), "late": sum(1 for c in cards if c["late"]),
            "budget": sum(b for pid, (b, _a) in costs.items() if pid in ids),
            "actual": sum(a for pid, (_b, a) in costs.items() if pid in ids),
            "high_risks": sum(n for pid, n in risks.items() if pid in ids)}


def today_iso() -> str:
    return date.today().isoformat()
