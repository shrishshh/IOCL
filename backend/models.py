from typing import Optional
from sqlmodel import SQLModel, Field


class Zone(SQLModel, table=True):
    __tablename__ = "zones"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)


class Office(SQLModel, table=True):
    __tablename__ = "offices"
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True)
    name: str
    city: str
    state: str
    zone_id: int = Field(foreign_key="zones.id")


class RO(SQLModel, table=True):
    __tablename__ = "ros"
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True)
    name: str
    office_id: int = Field(foreign_key="offices.id")
    profile: str


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True)
    password_hash: str
    role: str  # "inspector" | "zone_head" | "dept_officer"
    full_name: str
    office_id: Optional[int] = Field(default=None, foreign_key="offices.id")
    zone_id: Optional[int] = Field(default=None, foreign_key="zones.id")
    department: Optional[str] = Field(default=None)


class Inspection(SQLModel, table=True):
    __tablename__ = "inspections"
    id: Optional[int] = Field(default=None, primary_key=True)
    ro_id: int = Field(foreign_key="ros.id")
    submitted_by: int = Field(foreign_key="users.id")
    submitted_at: str
    overall_risk: str
    final_risk_index: float
    compliance_score: float
    numerical_risk_score: float
    semantic_risk_score: float
    hidden_risks: int
    label_counts_json: str


class InspectionItem(SQLModel, table=True):
    __tablename__ = "inspection_items"
    id: Optional[int] = Field(default=None, primary_key=True)
    inspection_id: int = Field(foreign_key="inspections.id", index=True)
    section: str
    item_id: str
    response: str
    remark: str
    predicted_label: str
    # Resolution workflow — only Medium/High items are resolvable
    resolved: bool = Field(default=False)
    resolved_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    resolved_by_name: Optional[str] = Field(default=None)   # snapshot of full_name at resolve time
    resolved_at: Optional[str] = Field(default=None)        # UTC ISO string


class DepartmentRisk(SQLModel, table=True):
    __tablename__ = "department_risks"
    id: Optional[int] = Field(default=None, primary_key=True)
    inspection_id: int = Field(foreign_key="inspections.id", index=True)
    department: str
    compliance: float
    numerical_risk: float
    semantic_risk: float
    final_index: float
    risk_band: str
    hidden_risks: int
