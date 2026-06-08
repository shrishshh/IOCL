import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..auth import require_role
from ..classifier import predict_labels
from ..database import get_session
from ..models import DepartmentRisk, Inspection, InspectionItem, RO, User
from ..risk_engine import assess, assess_by_department
from ..schemas import ChecklistItem

router = APIRouter(tags=["inspector"])

_inspector = require_role("inspector")


class _SubmitBody:
    pass


from pydantic import BaseModel


class InspectionSubmitRequest(BaseModel):
    ro_id: int
    items: list[ChecklistItem]


@router.get("/my/ros")
def my_ros(
    user: User = Depends(_inspector),
    session: Session = Depends(get_session),
):
    if not user.office_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Inspector has no office assigned")
    ros = session.exec(select(RO).where(RO.office_id == user.office_id)).all()
    return [
        {"ro_id": ro.id, "ro_code": ro.code, "ro_name": ro.name, "profile": ro.profile}
        for ro in ros
    ]


@router.post("/inspections", status_code=status.HTTP_201_CREATED)
def submit_inspection(
    req: InspectionSubmitRequest,
    user: User = Depends(_inspector),
    session: Session = Depends(get_session),
):
    ro = session.get(RO, req.ro_id)
    if not ro or ro.office_id != user.office_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "RO is not in your office")

    remarks = [it.remark for it in req.items]
    labels = predict_labels(remarks)

    items_with_labels = [
        {**it.model_dump(), "risk_label": lbl}
        for it, lbl in zip(req.items, labels)
    ]

    overall = assess(items_with_labels)
    dept_risk = assess_by_department(items_with_labels)

    insp = Inspection(
        ro_id=ro.id,
        submitted_by=user.id,
        submitted_at=datetime.now(timezone.utc).isoformat(),
        overall_risk=overall["overall_risk"],
        final_risk_index=overall["final_risk_index"],
        compliance_score=overall["compliance_score"],
        numerical_risk_score=overall["numerical_risk_score"],
        semantic_risk_score=overall["semantic_risk_score"],
        hidden_risks=overall["hidden_risks"],
        label_counts_json=json.dumps(overall["label_counts"]),
    )
    session.add(insp)
    session.flush()

    for item_dict in items_with_labels:
        session.add(InspectionItem(
            inspection_id=insp.id,
            section=item_dict["section"],
            item_id=item_dict["item_id"],
            response=item_dict["response"],
            remark=item_dict["remark"],
            predicted_label=item_dict["risk_label"],
        ))

    for dept, d in dept_risk.items():
        session.add(DepartmentRisk(
            inspection_id=insp.id,
            department=dept,
            compliance=d["compliance"],
            numerical_risk=d["numerical_risk"],
            semantic_risk=d["semantic_risk"],
            final_index=d["final_index"],
            risk_band=d["risk_band"],
            hidden_risks=d["hidden_risks"],
        ))

    session.commit()
    return {"status": "submitted", "inspection_id": insp.id}
