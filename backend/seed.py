"""
Idempotent seed script.
Run from repo root:  py -3.11 -m backend.seed

Populates:
  - zones, offices, ROs  (from IOCL_Inspection_Summary.csv)
  - demo users           (zone_heads × 5, inspectors × 20, dept_officers × 18)
  - ~40 historical inspections from IOCL_Inspection_Dataset.csv
    NOTE: Historical imports use the dataset's stored risk_level labels
    instead of re-running the BERT classifier to keep seeding under ~2 min.
    Live submissions from the app always use the BERT classifier.
"""

import csv
import sys
from pathlib import Path

# Allow running as a module from repo root
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from sqlmodel import Session, select

from backend.auth import hash_password
from backend.database import create_db_and_tables, engine
from backend.models import Inspection, Office, RO, User, Zone
from backend.risk_engine import DEPT_SECTIONS

_SUMMARY_CSV = _REPO / "NumericalAnalysis" / "IOCL_Inspection_Summary.csv"
_DEMO_PW = "demo1234"

# Zone display name → username slug
_ZONE_SLUG = {
    "Delhi NCR":             "zh_delhi_ncr",
    "Punjab Haryana Region": "zh_punjab_haryana",
    "Rajasthan Region":      "zh_rajasthan",
    "UP Region":             "zh_up",
    "Uttarakhand Region":    "zh_uttarakhand",
}
_ZONE_FULLNAME = {
    "Delhi NCR":             "Rajesh Kumar",
    "Punjab Haryana Region": "Gurpreet Singh",
    "Rajasthan Region":      "Vikram Meena",
    "UP Region":             "Anil Sharma",
    "Uttarakhand Region":    "Deepak Rawat",
}

_DEPARTMENTS = list(DEPT_SECTIONS.keys())
# Offices that get dept_officer demo users
_DEPT_OFFICES = ["OFF01", "OFF08"]


def _get_or_create_zone(session: Session, name: str) -> Zone:
    z = session.exec(select(Zone).where(Zone.name == name)).first()
    if not z:
        z = Zone(name=name)
        session.add(z)
        session.flush()
    return z


def _get_or_create_office(session, code, name, city, state, zone_id) -> Office:
    o = session.exec(select(Office).where(Office.code == code)).first()
    if not o:
        o = Office(code=code, name=name, city=city, state=state, zone_id=zone_id)
        session.add(o)
        session.flush()
    return o


def _get_or_create_ro(session, code, name, office_id, profile) -> RO:
    r = session.exec(select(RO).where(RO.code == code)).first()
    if not r:
        r = RO(code=code, name=name, office_id=office_id, profile=profile)
        session.add(r)
        session.flush()
    return r


def _get_or_create_user(session, username, role, full_name, pw,
                         office_id=None, zone_id=None, department=None) -> User:
    u = session.exec(select(User).where(User.username == username)).first()
    if not u:
        u = User(
            username=username,
            password_hash=hash_password(pw),
            role=role,
            full_name=full_name,
            office_id=office_id,
            zone_id=zone_id,
            department=department,
        )
        session.add(u)
        session.flush()
    return u



def seed():
    create_db_and_tables()

    with Session(engine) as session:
        # ── 1. Load org hierarchy from Summary CSV ────────────────────────────
        with open(_SUMMARY_CSV, newline="", encoding="utf-8") as f:
            summary_rows: list[dict] = list(csv.DictReader(f))

        # ── 2. Collect unique org entities ───────────────────────────────────
        zone_names = sorted({r["zone"] for r in summary_rows})
        offices_meta: dict[str, dict] = {}
        ros_meta: dict[str, dict] = {}

        for r in summary_rows:
            oc = r["office_id"]
            if oc not in offices_meta:
                offices_meta[oc] = {
                    "code": oc, "name": r["office_name"],
                    "city": r["city"], "state": r["state"], "zone": r["zone"],
                }
            rc = r["ro_id"]
            if rc not in ros_meta:
                ros_meta[rc] = {
                    "code": rc, "name": r["ro_name"],
                    "office_code": oc, "profile": r["ro_profile"],
                }

        # ── 3. Seed zones ─────────────────────────────────────────────────────
        zone_id_map: dict[str, int] = {}
        for zname in zone_names:
            z = _get_or_create_zone(session, zname)
            zone_id_map[zname] = z.id
        session.commit()
        print(f"  Zones:   {len(zone_id_map)}")

        # ── 4. Seed offices ───────────────────────────────────────────────────
        office_id_map: dict[str, int] = {}  # code → db id
        for oc, om in sorted(offices_meta.items()):
            o = _get_or_create_office(
                session, om["code"], om["name"],
                om["city"], om["state"], zone_id_map[om["zone"]],
            )
            office_id_map[om["code"]] = o.id
        session.commit()
        print(f"  Offices: {len(office_id_map)}")

        # ── 5. Seed ROs ───────────────────────────────────────────────────────
        ro_id_map: dict[str, int] = {}  # code → db id
        for rc, rm in sorted(ros_meta.items()):
            r = _get_or_create_ro(
                session, rm["code"], rm["name"],
                office_id_map[rm["office_code"]], rm["profile"],
            )
            ro_id_map[rm["code"]] = r.id
        session.commit()
        print(f"  ROs:     {len(ro_id_map)}")

        # ── 6. Seed zone heads (one per zone) ─────────────────────────────────
        credentials: list[tuple] = []  # (username, role, scope)
        for zname, zid in zone_id_map.items():
            uname = _ZONE_SLUG[zname]
            u = _get_or_create_user(
                session, uname, "zone_head", _ZONE_FULLNAME[zname],
                _DEMO_PW, zone_id=zid,
            )
            credentials.append((uname, "zone_head", f"Zone: {zname}"))
        session.commit()

        # ── 7. Seed inspectors (one per office) ───────────────────────────────
        inspector_id_map: dict[str, int] = {}  # office_code → user.id
        for oc in sorted(office_id_map.keys()):
            num = oc.lower()  # e.g. "off01"
            uname = f"insp_{num}"
            u = _get_or_create_user(
                session, uname, "inspector", f"Inspector {oc}",
                _DEMO_PW, office_id=office_id_map[oc],
            )
            inspector_id_map[oc] = u.id
            credentials.append((uname, "inspector", f"Office: {oc}"))
        session.commit()

        # ── 8. Seed dept officers (9 per demo office) ─────────────────────────
        for oc in _DEPT_OFFICES:
            for dept in _DEPARTMENTS:
                uname = f"dept_{dept.lower()}_{oc.lower()}"
                u = _get_or_create_user(
                    session, uname, "dept_officer",
                    f"{dept} Officer ({oc})", _DEMO_PW,
                    office_id=office_id_map[oc], department=dept,
                )
                credentials.append((uname, "dept_officer", f"Office: {oc} · Dept: {dept}"))
        session.commit()
        print(f"  Users:   {len(credentials)}")

        print("  Inspections: 0 (dashboards start empty — all data comes from live submissions)")

        # ── 10. Print credentials table ───────────────────────────────────────
        print()
        sep = "-" * 72
        print(sep)
        print(f"  {'USERNAME':<35} {'ROLE':<15} SCOPE")
        print(sep)
        for uname, role, scope in sorted(credentials):
            print(f"  {uname:<35} {role:<15} {scope}")
        print(sep)
        print(f"  Password for ALL accounts: {_DEMO_PW}")
        print(sep)
        print()


if __name__ == "__main__":
    print("\nSeeding IOCL database…")
    seed()
    print("Done.\n")
