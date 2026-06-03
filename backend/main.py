from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .schemas import AssessRequest, AssessResponse
from .classifier import predict_labels
from .risk_engine import assess

_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="IOCL Safety Risk Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/assess", response_model=AssessResponse)
def assess_inspection(req: AssessRequest):
    remarks = [item.remark for item in req.items]
    labels = predict_labels(remarks)

    items_with_labels = [
        {**item.model_dump(), "risk_label": label}
        for item, label in zip(req.items, labels)
    ]

    result = assess(items_with_labels)
    result["inspection_id"] = req.inspection_id
    result["ro_name"] = req.ro_name
    return result


# Serve PWA — mount after API routes so /assess isn't shadowed
app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
