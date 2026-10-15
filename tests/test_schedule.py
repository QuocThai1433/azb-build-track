from datetime import date, datetime, timedelta

import pytest

from azb_hub import repositories as repo
from azb_hub.db import SessionLocal
from azb_hub.models import Baseline, Cost, Project, Task, TaskDependency
from azb_hub.services import backup, control, scheduling


def cal(first="2026-01-05", last="2026-06-30", holidays=()):
    return scheduling.WorkCalendar(date.fromisoformat(first), date.fromisoformat(last),
                                   scheduling.DEFAULT_WORK_DAYS, holidays)


def T(i, s, e):
    return {"id": i, "start_date": s, "end_date": e}


# ---- pure CPM ---------------------------------------------------------------------------------

def test_calendar_skips_sunday_and_holidays():
    c = cal(holidays=["2026-01-07"])
    # Mon 5 .. Sat 10, minus Wed 7 holiday = 5 working days
    assert c.count(date(2026, 1, 5), date(2026, 1, 10)) == 5
    assert c.count(date(2026, 1, 11), date(2026, 1, 11)) == 0          # Sunday


def test_finish_start_chain_pushes_successor_and_marks_critical():
    tasks = [T(1, "2026-01-05", "2026-01-09"), T(2, "2026-01-05", "2026-01-07"), T(3, "2026-01-12", "2026-01-14")]
    res = scheduling.compute(tasks, [(1, 2, "FS", 0), (2, 3, "FS", 0)], cal())
    assert res[2].es == date(2026, 1, 10)             # day after task 1 finishes (Sat is a work day)
    assert res[2].shift > 0
    assert res[1].critical and res[2].critical and res[3].critical


def test_parallel_task_has_float():
    tasks = [T(1, "2026-01-05", "2026-01-30"), T(2, "2026-01-05", "2026-01-09"), T(3, "2026-01-31", "2026-02-06")]
    res = scheduling.compute(tasks, [(1, 3, "FS", 0), (2, 3, "FS", 0)], cal())
    assert res[1].critical
    assert not res[2].critical and res[2].total_float > 0


def test_lag_and_ss_ff_types():
    tasks = [T(1, "2026-01-05", "2026-01-16"), T(2, "2026-01-05", "2026-01-09")]
    ss = scheduling.compute(tasks, [(1, 2, "SS", 3)], cal())
    assert ss[2].es == cal().date_of(cal().next_idx(date(2026, 1, 5)) + 3)
    ff = scheduling.compute(tasks, [(1, 2, "FF", 0)], cal())
    assert ff[2].ef == ff[1].ef


def test_cycle_is_rejected():
    assert scheduling.would_cycle([(1, 2), (2, 3)], 3, 1)
    assert not scheduling.would_cycle([(1, 2)], 1, 3)
    with pytest.raises(scheduling.CycleError):
        scheduling.compute([T(1, "2026-01-05", "2026-01-06"), T(2, "2026-01-05", "2026-01-06")],
                           [(1, 2, "FS", 0), (2, 1, "FS", 0)], cal())


# ---- with the database ------------------------------------------------------------------------

@pytest.fixture()
def pid():
    with SessionLocal() as db:
        p = Project(name="Dự án kiểm soát tiến độ", start_date="2026-01-05", end_date="2026-02-27")
        db.add(p)
        db.commit()
        for i, (s, e) in enumerate([("2026-01-05", "2026-01-16"), ("2026-01-19", "2026-01-30"),
                                    ("2026-02-02", "2026-02-27")], 1):
            db.add(Task(project_id=p.id, title=f"Việc {i}", start_date=s, end_date=e, weight=1.0 + i))
        db.add(Cost(project_id=p.id, name="Chi phí", budget_amount=1000, actual_amount=300))
        db.commit()
        return p.id


def test_progress_is_weighted_and_evm_values(pid):
    with SessionLocal() as db:
        tasks = control.detail_tasks(db, pid)
        tasks[0].actual_progress = 100          # weight 2 of 2+3+4
        db.commit()
        assert control.actual_progress(tasks) == pytest.approx(2 / 9)
        m = control.evm(db, pid, tasks, date(2026, 1, 20))
        assert m["bac"] == 1000 and m["ac"] == 300
        assert m["ev"] == pytest.approx(1000 * 2 / 9)
        assert m["cpi"] == pytest.approx(m["ev"] / 300)


def test_schedule_page_dependencies_baseline_and_gantt(client, pid):
    with SessionLocal() as db:
        ids = [t.id for t in control.detail_tasks(db, pid)]
        slug = repo.get_project(db, pid).slug
    r = client.post(f"/{slug}/schedule/dependencies", data={
        "predecessor_id": ids[0], "successor_id": ids[1], "dep_type": "FS", "lag_days": 0})
    assert r.status_code == 303
    client.post(f"/{slug}/schedule/dependencies", data={"predecessor_id": ids[1], "successor_id": ids[2]})
    # a loop is refused
    client.post(f"/{slug}/schedule/dependencies", data={"predecessor_id": ids[2], "successor_id": ids[0]})
    with SessionLocal() as db:
        assert db.query(TaskDependency).filter_by(project_id=pid).count() == 2

    assert client.post(f"/{slug}/schedule/baselines", data={"name": "Gốc"}).status_code == 303
    with SessionLocal() as db:
        assert db.query(Baseline).filter_by(project_id=pid, is_active=True).count() == 1

    page = client.get(f"/{slug}/schedule")
    assert page.status_code == 200
    assert "Đường cong S" in page.text and "Gốc" in page.text

    gantt = client.get(f"/{slug}/gantt")
    assert gantt.status_code == 200
    assert "ganttDeps" in gantt.text and "gantt-baseline-bar" in gantt.text


def test_holiday_and_calendar_forms(client, pid):
    with SessionLocal() as db:
        slug = repo.get_project(db, pid).slug
    assert client.post(f"/{slug}/schedule/holidays", data={
        "day": "2026-01-26", "end_day": "2026-01-28", "name": "Nghỉ"}).status_code == 303
    assert client.post(f"/{slug}/schedule/calendar", data={"work_days": ["0", "1", "2", "3", "4"]}).status_code == 303
    with SessionLocal() as db:
        assert len(control.list_holidays(db, pid)) == 3
        assert repo.get_project(db, pid).work_days == "0,1,2,3,4"


def test_auto_backup_runs_once_per_day(monkeypatch, tmp_path):
    monkeypatch.setattr(backup, "backups_dir", lambda: tmp_path)
    created = []
    monkeypatch.setattr(backup, "create_backup", lambda label="": created.append(label) or
                        (tmp_path / f"{backup.DB_PATH.stem}_{label}_x{len(created)}.db").write_bytes(b"x"))
    now = datetime.now()
    assert backup.backup_if_due(now) is None or created
    first = len(created)
    backup.backup_if_due(now + timedelta(minutes=5))
    assert len(created) == first                           # still fresh: no second file


def test_reimport_keeps_dependencies_baseline_and_weight(client, pid):
    from azb_hub.models import BaselineTask
    from azb_hub.services import excel_import
    with SessionLocal() as db:
        tasks = control.detail_tasks(db, pid)
        for n, t in enumerate(tasks, 1):
            t.source_id = n * 10
        tasks[0].weight = 5.0
        db.add(TaskDependency(project_id=pid, predecessor_id=tasks[0].id, successor_id=tasks[1].id))
        db.commit()
        control.create_baseline(db, pid, "G", "t")
        rows = [{"source_id": t.source_id, "title": t.title, "start_date": t.start_date, "end_date": t.end_date,
                 "task_type": "Chi tiết"} for t in tasks]
        from azb_hub.services.excel_mapping import EntityPlan
        plan = EntityPlan(entity="tasks", label="Tiến độ", rows=rows,
                          mapped_fields={"title", "start_date", "end_date", "source_id"})
        excel_import._apply_tasks(db, pid, plan, {"matched_id": 0, "matched_title": 0})
        db.commit()
        new = {t.source_id: t for t in control.detail_tasks(db, pid)}
        assert new[10].weight == 5.0
        deps = db.query(TaskDependency).filter_by(project_id=pid).all()
        assert [(d.predecessor_id, d.successor_id) for d in deps] == [(new[10].id, new[20].id)]
        assert db.query(BaselineTask).filter(BaselineTask.task_id.in_([t.id for t in new.values()])).count() == 3
