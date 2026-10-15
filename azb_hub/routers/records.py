"""Resources, costs, risks and construction methods: list page + the same new/edit/delete trio."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..constants import PRIORITIES, RISK_STATUSES
from .. import auth
from ..db import get_db
from ..models import Cost, Method, Resource, Risk
from ..schemas import CostForm, MethodForm, ResourceForm, RiskForm
from ..web import flash, or_404, redirect, render
from .deps import require

router = APIRouter()


@dataclass
class Crud:
    prefix: str                       # route names: <prefix>_new / _edit / _delete
    path: str                         # URL base, e.g. "/resources"
    list_route: str
    model: type
    form_cls: type
    template: str
    new_title: str
    edit_title: str
    required_message: str
    added: str
    updated: str
    deleted: str
    required_field: str = "name"
    prepare: Callable[[dict[str, Any], bool], dict[str, Any]] = lambda values, creating: values
    extra: dict[str, Any] = field(default_factory=dict)


def register(c: Crud) -> None:
    FormBody = Annotated[c.form_cls, Form()]

    def page(request: Request, title: str, item):
        return render(request, c.template, title=title, item=item, **c.extra)

    def new_page(request: Request, project_id: int):
        return page(request, c.new_title, None)

    def create(request: Request, project_id: int, form: FormBody, db: Session = Depends(get_db)):
        values = c.prepare(form.model_dump(), True)
        if c.model is Cost:       # a cost entered by staff waits for the director's approval
            values["approval_status"] = "da_duyet" if auth.can(request.state.user, "cost.approve") else "cho_duyet"
        if not str(values[c.required_field] or "").strip():
            flash(request, c.required_message, "error")
            return page(request, c.new_title, None)
        repo.create(db, c.model, project_id, values)
        flash(request, c.added, "success")
        return redirect(request, c.list_route)

    def edit_page(request: Request, project_id: int, record_id: int, db: Session = Depends(get_db)):
        return page(request, c.edit_title, or_404(repo.get(db, c.model, project_id, record_id)))

    def save(request: Request, project_id: int, record_id: int, form: FormBody, db: Session = Depends(get_db)):
        item = or_404(repo.get(db, c.model, project_id, record_id))
        values = c.prepare(form.model_dump(), False)
        if c.model is Cost and not auth.can(request.state.user, "cost.approve"):
            values.update(approval_status="cho_duyet", approved_by=None, approved_at=None, approval_note=None)
        repo.update(db, item, values)
        flash(request, c.updated, "success")
        return redirect(request, c.list_route)

    def delete(request: Request, project_id: int, record_id: int, db: Session = Depends(get_db)):
        repo.remove(db, c.model, project_id, record_id)
        flash(request, c.deleted, "success")
        return redirect(request, c.list_route)

    router.add_api_route(f"{c.path}/new", new_page, methods=["GET"], name=f"{c.prefix}_new", include_in_schema=False)
    router.add_api_route(f"{c.path}/new", create, methods=["POST"], name=f"{c.prefix}_new", include_in_schema=False)
    router.add_api_route(f"{c.path}/{{record_id}}/edit", edit_page, methods=["GET"], name=f"{c.prefix}_edit", include_in_schema=False)
    router.add_api_route(f"{c.path}/{{record_id}}/edit", save, methods=["POST"], name=f"{c.prefix}_edit", include_in_schema=False)
    router.add_api_route(f"{c.path}/{{record_id}}/delete", delete, methods=["POST"], name=f"{c.prefix}_delete",
                         include_in_schema=False, dependencies=[Depends(require("record.delete"))])


def _risk_values(values: dict[str, Any], creating: bool) -> dict[str, Any]:
    values["description"] = values["description"].strip()
    if creating:
        values["created_at"] = datetime.now().isoformat(timespec="seconds")
    return values


def _method_values(values: dict[str, Any], creating: bool) -> dict[str, Any]:
    if creating:
        values["name"] = values["name"].strip()
    return values


register(Crud(prefix="resource", path="/resources", list_route="resources_list", model=Resource,
              form_cls=ResourceForm, template="resource_form.html", new_title="Thêm nguồn lực",
              edit_title="Cập nhật nguồn lực", required_message="Vui lòng nhập tên nguồn lực.",
              added="Đã thêm nguồn lực.", updated="Đã cập nhật nguồn lực.", deleted="Đã xóa nguồn lực."))
register(Crud(prefix="cost", path="/costs", list_route="costs_list", model=Cost,
              form_cls=CostForm, template="cost_form.html", new_title="Thêm khoản chi",
              edit_title="Cập nhật khoản chi", required_message="Vui lòng nhập tên khoản chi.",
              added="Đã thêm khoản chi.", updated="Đã cập nhật khoản chi.", deleted="Đã xóa khoản chi."))
register(Crud(prefix="risk", path="/risks", list_route="risks_list", model=Risk,
              form_cls=RiskForm, template="risk_form.html", new_title="Thêm rủi ro",
              edit_title="Cập nhật rủi ro", required_message="Vui lòng mô tả rủi ro.",
              required_field="description", prepare=_risk_values,
              added="Đã ghi nhận rủi ro.", updated="Đã cập nhật rủi ro.", deleted="Đã xóa rủi ro.",
              extra={"severities": PRIORITIES, "risk_statuses": RISK_STATUSES}))
register(Crud(prefix="method", path="/methods", list_route="methods_list", model=Method,
              form_cls=MethodForm, template="method_form.html", new_title="Thêm hạng mục",
              edit_title="Cập nhật hạng mục", required_message="Vui lòng nhập hạng mục.",
              prepare=_method_values,
              added="Đã thêm biện pháp/hạng mục.", updated="Đã cập nhật hạng mục.", deleted="Đã xóa hạng mục."))


@router.get("/resources", name="resources_list")
def resources_list(request: Request, project_id: int, db: Session = Depends(get_db), q: str = "",
                   typ: Annotated[str, Query(alias="type")] = ""):
    q, typ = q.strip(), typ.strip()
    return render(request, "resources.html", title="Nguồn lực", items=repo.list_resources(db, project_id, q, typ),
                  types=repo.resource_types(db, project_id), q=q, typ=typ)


@router.get("/costs", name="costs_list")
def costs_list(request: Request, project_id: int, db: Session = Depends(get_db), q: str = ""):
    q = q.strip()
    return render(request, "costs.html", title="Chi phí", items=repo.list_costs(db, project_id, q),
                  sums=repo.cost_totals(db, project_id), q=q)


@router.get("/risks", name="risks_list")
def risks_list(request: Request, project_id: int, db: Session = Depends(get_db), q: str = "", severity: str = "",
               status: str = ""):
    q, severity, status = q.strip(), severity.strip(), status.strip()
    return render(request, "risks.html", title="Rủi ro & kiến nghị",
                  items=repo.list_risks(db, project_id, q, severity, status), counts=repo.risk_counts(db, project_id),
                  q=q, severity=severity, status=status, severities=PRIORITIES, risk_statuses=RISK_STATUSES)


@router.get("/methods", name="methods_list")
def methods_list(request: Request, project_id: int, db: Session = Depends(get_db), q: str = ""):
    q = q.strip()
    return render(request, "methods.html", title="Biện pháp thi công", items=repo.list_methods(db, project_id, q), q=q)


@router.post("/costs/{record_id}/approval", name="cost_approval", dependencies=[Depends(require("cost.approve"))])
def cost_approval(request: Request, project_id: int, record_id: int, decision: Annotated[str, Form()] = "",
                  note: Annotated[str, Form()] = "", db: Session = Depends(get_db)):
    """The director approves or rejects a cost entered by staff. Both are written to the audit log."""
    item = or_404(repo.get(db, Cost, project_id, record_id))
    if decision not in ("approve", "reject"):
        flash(request, "Quyết định duyệt không hợp lệ.", "error")
        return redirect(request, "costs_list")
    user = request.state.user
    repo.set_cost_approval(db, item, "da_duyet" if decision == "approve" else "tu_choi",
                           user.full_name or user.username, note.strip()[:300])
    flash(request, "Đã duyệt khoản chi." if decision == "approve" else "Đã từ chối khoản chi.", "success")
    return redirect(request, "costs_list")
