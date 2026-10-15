"""Form models. Validators are lenient on purpose: Vietnamese users type ``1,5`` and leave dates empty."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator


def parse_float(value, default: float | None = 0.0):
    try:
        return float(str(value or "0").replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _to_float(value) -> float:
    return parse_float(value)


def _to_date(value) -> str | None:
    value = (value or "").strip() if isinstance(value, str) else value
    return value or None


def _to_optional_int(value) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    number = parse_float(value, None)
    return None if number is None else int(number)


Num = Annotated[float, BeforeValidator(_to_float)]
OptDate = Annotated[str | None, BeforeValidator(_to_date)]
OptInt = Annotated[int | None, BeforeValidator(_to_optional_int)]


class ProjectForm(BaseModel):
    name: str = ""
    client: str = ""
    contractor: str = ""
    package_name: str = ""
    description: str = ""
    start_date: OptDate = None
    end_date: OptDate = None
    report_date: OptDate = None
    contract_value: Num = 0.0
    prelim_budget: Num = 0.0
    notes: str = ""
    construction_status: str = "dang_thi_cong"


class TaskForm(BaseModel):
    source_id: OptInt = None
    category: str = ""
    title: str = ""
    task_type: str = "Chi tiết"
    planned_days: Num = 0.0
    start_date: OptDate = None
    end_date: OptDate = None
    plan_progress: Num = 0.0
    plan_status: str = ""
    float_days: Num = 0.0
    notes: str = ""
    actual_progress: Num = 0.0
    actual_status: str = "Chưa cập nhật"
    owner: str = ""
    actual_start_date: OptDate = None
    actual_end_date: OptDate = None
    priority: str = "Trung bình"
    weight: Num = 1.0


class ResourceForm(BaseModel):
    name: str = ""
    resource_type: str = "Nhân sự"
    group_name: str = ""
    quantity: Num = 0.0
    duration_months: Num = 0.0
    start_date: OptDate = None
    end_date: OptDate = None
    unit: str = "người"
    cost: Num = 0.0
    notes: str = ""


class CostForm(BaseModel):
    name: str = ""
    category: str = "Chi phí khác"
    unit: str = ""
    quantity: Num = 0.0
    unit_price: Num = 0.0
    budget_amount: Num = 0.0
    actual_amount: Num = 0.0
    notes: str = ""


class RiskForm(BaseModel):
    category: str = "Dữ liệu"
    description: str = ""
    basis: str = ""
    severity: str = "Trung bình"
    recommendation: str = ""
    owner: str = ""
    due_date: OptDate = None
    status: str = "Chưa xử lý"


class MethodForm(BaseModel):
    name: str = ""
    unit: str = ""
    quantity: Num = 0.0
    specification: str = ""
    schedule: str = ""
    source: str = ""


class HsseForm(BaseModel):
    log_date: OptDate = None
    log_type: str = "Kiểm tra an toàn"
    description: str = ""
    people_affected: Num = 0.0
    severity: str = "Thấp"
    status: str = "Đã ghi nhận"
    reporter: str = ""


class DiaryForm(BaseModel):
    log_date: OptDate = None
    weather: str = ""
    worker_count: Num = 0.0
    completed_work: str = ""
    issues: str = ""
    reporter: str = ""
