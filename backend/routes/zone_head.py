import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..auth import require_role
from ..database import get_session
from ..models import DepartmentRisk, Inspection, InspectionItem, Office, RO, User
from ..risk_engine import section_scores

router = APIRouter(tags=["zone_head"])

_zh = require_role("zone_head")


def _zone_ro_ids(user: User, session: Session) -> list[int]:
    offices = session.exec(select(Office).where(Office.zone_id == user.zone_id)).all()
    office_ids = [o.id for o in offices]
    ros = session.exec(select(RO).where(RO.office_id.in_(office_ids))).all()
    return [r.id for r in ros]


def _ro_map(ro_ids: list[int], session: Session) -> dict[int, RO]:
    ros = session.exec(select(RO).where(RO.id.in_(ro_ids))).all()
    return {r.id: r for r in ros}


@router.get("/zone/inspections")
def list_zone_inspections(
    user: User = Depends(_zh),
    session: Session = Depends(get_session),
):
    ro_ids = _zone_ro_ids(user, session)
    if not ro_ids:
        return []
    inspections = session.exec(
        select(Inspection).where(Inspection.ro_id.in_(ro_ids))
    ).all()
    ro_m = _ro_map(ro_ids, session)
    return [
        {
            "id": insp.id,
            "ro_name": ro_m[insp.ro_id].name,
            "ro_code": ro_m[insp.ro_id].code,
            "submitted_at": insp.submitted_at,
            "overall_risk": insp.overall_risk,
            "final_risk_index": insp.final_risk_index,
            "compliance_score": insp.compliance_score,
        }
        for insp in inspections
    ]


@router.get("/inspections/{insp_id}")
def get_inspection_detail(
    insp_id: int,
    user: User = Depends(_zh),
    session: Session = Depends(get_session),
):
    insp = session.get(Inspection, insp_id)
    if not insp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inspection not found")

    ro = session.get(RO, insp.ro_id)
    office = session.get(Office, ro.office_id)
    if office.zone_id != user.zone_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Inspection is outside your zone")

    db_items = session.exec(
        select(InspectionItem).where(InspectionItem.inspection_id == insp_id)
    ).all()
    dept_risks = session.exec(
        select(DepartmentRisk).where(DepartmentRisk.inspection_id == insp_id)
    ).all()

    items_dicts = [
        {
            "section": it.section,
            "item_id": it.item_id,
            "response": it.response,
            "remark": it.remark,
            "risk_label": it.predicted_label,
        }
        for it in db_items
    ]
    secs = section_scores(items_dicts)
    flags = {s: v for s, v in sorted(secs.items(), key=lambda x: x[1]) if v < 70}

    return {
        "id": insp.id,
        "ro_name": ro.name,
        "ro_code": ro.code,
        "submitted_at": insp.submitted_at,
        "overall_risk": insp.overall_risk,
        "final_risk_index": insp.final_risk_index,
        "compliance_score": insp.compliance_score,
        "numerical_risk_score": insp.numerical_risk_score,
        "semantic_risk_score": insp.semantic_risk_score,
        "hidden_risks": insp.hidden_risks,
        "label_counts": json.loads(insp.label_counts_json),
        "section_flags": flags,
        "items": [
            {
                "section": it.section,
                "item_id": it.item_id,
                "response": it.response,
                "remark": it.remark,
                "predicted_label": it.predicted_label,
            }
            for it in db_items
        ],
        "department_risks": [
            {
                "department": dr.department,
                "compliance": dr.compliance,
                "numerical_risk": dr.numerical_risk,
                "semantic_risk": dr.semantic_risk,
                "final_index": dr.final_index,
                "risk_band": dr.risk_band,
                "hidden_risks": dr.hidden_risks,
            }
            for dr in dept_risks
        ],
    }
