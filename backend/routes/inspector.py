import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import require_role
from ..classifier import predict_labels
from ..database import engine, get_session
from ..models import DepartmentRisk, Inspection, InspectionItem, RO, User
from ..risk_engine import assess, assess_by_department
from ..schemas import ChecklistItem

router = APIRouter(tags=["inspector"])

_inspector = require_role("inspector")

# Try to import RAG recommend at startup; if deps aren't installed, degrade gracefully.
try:
    from ..rag.recommend import recommend_for_item as _recommend
    _RAG_AVAILABLE = True
except Exception:
    _RAG_AVAILABLE = False


class InspectionSubmitRequest(BaseModel):
    ro_id: int
    items: list[ChecklistItem]


def _generate_recommendations(inspection_id: int) -> None:
    """Background task: generate OISD-STD-225 RAG recommendations for Medium/High items."""
    if not _RAG_AVAILABLE:
        return
    with Session(engine) as session:
        items = session.exec(
            select(InspectionItem).where(
                InspectionItem.inspection_id == inspection_id,
                InspectionItem.predicted_label.in_(["Medium", "High"]),
            )
        ).all()
        changed = False
        for item in items:
            try:
                result = _recommend(
                    question  =item.question or "",
                    response  =item.response,
                    remark    =item.remark,
                    risk_label=item.predicted_label,
                    section   =item.section,
                )
                item.recommendation          = result.get("text")
                item.recommendation_sections = json.dumps(result.get("cited_sections", []))
                session.add(item)
                changed = True
            except Exception:
                pass
        if changed:
            try:
                session.commit()
            except Exception:
                pass


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
    background_tasks: BackgroundTasks,
    user: User = Depends(_inspector),
    session: Session = Depends(get_session),
):
    ro = session.get(RO, req.ro_id)
    if not ro or ro.office_id != user.office_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "RO is not in your office")

    remarks = [it.remark for it in req.items]
    labels  = predict_labels(remarks)

    items_with_labels = [
        {**it.model_dump(), "risk_label": lbl}
        for it, lbl in zip(req.items, labels)
    ]

    overall  = assess(items_with_labels)
    dept_risk = assess_by_department(items_with_labels)

    insp = Inspection(
        ro_id                =ro.id,
        submitted_by         =user.id,
        submitted_at         =datetime.now(timezone.utc).isoformat(),
        overall_risk         =overall["overall_risk"],
        final_risk_index     =overall["final_risk_index"],
        compliance_score     =overall["compliance_score"],
        numerical_risk_score =overall["numerical_risk_score"],
        semantic_risk_score  =overall["semantic_risk_score"],
        hidden_risks         =overall["hidden_risks"],
        label_counts_json    =json.dumps(overall["label_counts"]),
    )
    session.add(insp)
    session.flush()

    for item_dict in items_with_labels:
        session.add(InspectionItem(
            inspection_id =insp.id,
            section       =item_dict["section"],
            item_id       =item_dict["item_id"],
            question      =item_dict.get("question", ""),
            response      =item_dict["response"],
            remark        =item_dict["remark"],
            predicted_label=item_dict["risk_label"],
        ))

    for dept, d in dept_risk.items():
        session.add(DepartmentRisk(
            inspection_id=insp.id,
            department   =dept,
            compliance   =d["compliance"],
            numerical_risk=d["numerical_risk"],
            semantic_risk=d["semantic_risk"],
            final_index  =d["final_index"],
            risk_band    =d["risk_band"],
            hidden_risks =d["hidden_risks"],
        ))

    session.commit()

    # Fire background task — returns immediately; recommendations fill in within seconds.
    background_tasks.add_task(_generate_recommendations, insp.id)

    return {"status": "submitted", "inspection_id": insp.id}
