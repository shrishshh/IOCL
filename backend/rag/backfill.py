"""
Backfill RAG recommendations for any inspection_items that have
recommendation = NULL (e.g. from a submit that ran before the API key was set).

Run from repo root:
    py -3.11 -m backend.rag.backfill
"""
import json
import sys

from sqlmodel import Session, select

from ..database import engine
from ..models import InspectionItem
from .recommend import recommend_for_item


def backfill() -> None:
    with Session(engine) as session:
        items = session.exec(
            select(InspectionItem).where(
                InspectionItem.predicted_label.in_(["Medium", "High"]),
                InspectionItem.recommendation.is_(None),
            )
        ).all()

        total = len(items)
        if total == 0:
            print("[backfill] No null recommendations found — nothing to do.")
            return

        print(f"[backfill] {total} items need recommendations. Generating…")
        ok = fail = 0
        for i, item in enumerate(items, 1):
            try:
                result = recommend_for_item(
                    question  =item.question or "",
                    response  =item.response,
                    remark    =item.remark,
                    risk_label=item.predicted_label,
                    section   =item.section,
                )
                item.recommendation          = result.get("text")
                item.recommendation_sections = json.dumps(result.get("cited_sections", []))
                session.add(item)
                if result.get("text"):
                    ok += 1
                    print(f"  [{i}/{total}] {item.item_id} ✓")
                else:
                    fail += 1
                    print(f"  [{i}/{total}] {item.item_id} — LLM returned None (key missing or vectorstore empty)")
            except Exception as e:
                fail += 1
                print(f"  [{i}/{total}] {item.item_id} ERROR: {e}")

        session.commit()
        print(f"[backfill] Done. {ok} generated, {fail} failed.")


if __name__ == "__main__":
    backfill()
