from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..auth import require_role
from ..database import get_session
from ..models import DepartmentRisk, Inspection, InspectionItem, Office, RO, User
from ..risk_engine import DEPT_SECTIONS

router = APIRouter(tags=["dept_officer"])

_do = require_role("dept_officer")

_RESOLVABLE = {"Medium", "High"}


def _office_ro_ids(user: User, session: Session) -> list[int]:
    ros = session.exec(select(RO).where(RO.office_id == user.office_id)).all()
    return [r.id for r in ros]


def _ro_map(ro_ids: list[int], session: Session) -> dict[int, RO]:
    ros = session.exec(select(RO).where(RO.id.in_(ro_ids))).all()
    return {r.id: r for r in ros}


def _ser_item(it: InspectionItem) -> dict:
    return {
        "id": it.id,
        "item_id": it.item_id,
        "section": it.section,
        "response": it.response,
        "remark": it.remark,
        "predicted_label": it.predicted_label,
        "resolved": it.resolved,
        "resolved_by_name": it.resolved_by_name,
        "resolved_at": it.resolved_at,
    }


@router.get("/dept/inspections")
def list_dept_inspections(
    user: User = Depends(_do),
    session: Session = Depends(get_session),
):
    if not user.office_id or not user.department:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dept officer missing office or department")

    ro_ids = _office_ro_ids(user, session)
    if not ro_ids:
        return []

    inspections = session.exec(
        select(Inspection).where(Inspection.ro_id.in_(ro_ids))
    ).all()
    insp_ids = [i.id for i in inspections]
    ro_m = _ro_map(ro_ids, session)

    dept_risks = session.exec(
        select(DepartmentRisk).where(
            DepartmentRisk.inspection_id.in_(insp_ids),
            DepartmentRisk.department == user.department,
        )
    ).all()
    dr_map = {dr.inspection_id: dr for dr in dept_risks}

    result = []
    for insp in sorted(inspections, key=lambda i: i.submitted_at, reverse=True):
        dr = dr_map.get(insp.id)
        result.append({
            "id": insp.id,
            "ro_name": ro_m[insp.ro_id].name,
            "ro_code": ro_m[insp.ro_id].code,
            "submitted_at": insp.submitted_at,
            "dept_risk_band": dr.risk_band if dr else None,
            "dept_final_index": dr.final_index if dr else None,
        })
    return result


@router.get("/dept/inspections/{insp_id}")
def get_dept_inspection_detail(
    insp_id: int,
    user: User = Depends(_do),
    session: Session = Depends(get_session),
):
    if not user.office_id or not user.department:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dept officer missing office or department")

    insp = session.get(Inspection, insp_id)
    if not insp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inspection not found")

    ro = session.get(RO, insp.ro_id)
    if ro.office_id != user.office_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Inspection is outside your office")

    dept_section = DEPT_SECTIONS.get(user.department)
    if not dept_section:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown department")

    dept_items = session.exec(
        select(InspectionItem).where(
            InspectionItem.inspection_id == insp_id,
            InspectionItem.section == dept_section,
        )
    ).all()

    dr = session.exec(
        select(DepartmentRisk).where(
            DepartmentRisk.inspection_id == insp_id,
            DepartmentRisk.department == user.department,
        )
    ).first()

    return {
        "id": insp.id,
        "ro_name": ro.name,
        "submitted_at": insp.submitted_at,
        "department": user.department,
        "dept_risk": {
            "compliance": dr.compliance if dr else None,
            "numerical_risk": dr.numerical_risk if dr else None,
            "semantic_risk": dr.semantic_risk if dr else None,
            "final_index": dr.final_index if dr else None,
            "risk_band": dr.risk_band if dr else None,
            "hidden_risks": dr.hidden_risks if dr else None,
        },
        "items": [_ser_item(it) for it in dept_items],
    }


@router.post("/dept/inspections/{insp_id}/items/{item_db_id}/resolve")
def resolve_item(
    insp_id: int,
    item_db_id: int,
    user: User = Depends(_do),
    session: Session = Depends(get_session),
):
    if not user.office_id or not user.department:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dept officer missing office or department")

    insp = session.get(Inspection, insp_id)
    if not insp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inspection not found")

    ro = session.get(RO, insp.ro_id)
    if ro.office_id != user.office_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Inspection is outside your office")

    item = session.get(InspectionItem, item_db_id)
    if not item or item.inspection_id != insp_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found in this inspection")

    dept_section = DEPT_SECTIONS.get(user.department)
    if item.section != dept_section:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Item is not in your department")

    if item.predicted_label not in _RESOLVABLE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only Medium/High items can be resolved")

    # Idempotent — re-resolving is a no-op
    if not item.resolved:
        item.resolved = True
        item.resolved_by_user_id = user.id
        item.resolved_by_name = user.full_name
        item.resolved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        session.add(item)
        session.commit()
        session.refresh(item)

    return _ser_item(item)
