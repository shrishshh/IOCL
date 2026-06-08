"""Quick smoke test - run while server is up on port 8000."""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"

ITEMS = [
    {"section": "PPE", "item_id": "A1",  "response": "Yes", "remark": "All fine."},
    {"section": "PPE", "item_id": "A2",  "response": "Yes", "remark": "OK"},
    {"section": "PPE", "item_id": "A3",  "response": "No",  "remark": "Missing coverall."},
    {"section": "PPE", "item_id": "B1",  "response": "Yes", "remark": "Present."},
    {"section": "PPE", "item_id": "B2",  "response": "Yes", "remark": "OK"},
    {"section": "PPE", "item_id": "B3",  "response": "Yes", "remark": "OK"},
    {"section": "PPE", "item_id": "B4",  "response": "NA",  "remark": ""},
    {"section": "PPE", "item_id": "B5",  "response": "Yes", "remark": "OK"},
    {"section": "PPE", "item_id": "B6",  "response": "Yes", "remark": "OK"},
    {"section": "PPE", "item_id": "B8",  "response": "Yes", "remark": "OK"},
    {"section": "PPE", "item_id": "B9",  "response": "Yes", "remark": "OK"},
    {"section": "PPE", "item_id": "B10", "response": "Yes", "remark": "OK"},
    {"section": "PPE", "item_id": "C1",  "response": "Yes", "remark": "Trained."},
    {"section": "PPE", "item_id": "C2",  "response": "Yes", "remark": "System in place."},
    {"section": "Housekeeping", "item_id": "HK1", "response": "Yes", "remark": "Good"},
    {"section": "Housekeeping", "item_id": "HK2", "response": "Yes", "remark": "Marked"},
    {"section": "Housekeeping", "item_id": "HK3", "response": "Yes", "remark": "Regular"},
    {"section": "Housekeeping", "item_id": "HK4", "response": "Yes", "remark": "Clear"},
    {"section": "Housekeeping", "item_id": "HK5", "response": "Yes", "remark": "Done"},
    {"section": "Housekeeping", "item_id": "HK6", "response": "Yes", "remark": "In place"},
    {"section": "Housekeeping", "item_id": "HK7", "response": "Yes", "remark": "Clean"},
    {"section": "Housekeeping", "item_id": "HK8", "response": "Yes", "remark": "Proper"},
    {"section": "Excavation", "item_id": "EX1", "response": "Yes", "remark": "Approved"},
    {"section": "Excavation", "item_id": "EX2", "response": "Yes", "remark": "Obtained"},
    {"section": "Excavation", "item_id": "EX3", "response": "Yes", "remark": "Done"},
    {"section": "Excavation", "item_id": "EX4", "response": "Yes", "remark": "Provided"},
    {"section": "Excavation", "item_id": "EX5", "response": "Yes", "remark": "Provided"},
    {"section": "Excavation", "item_id": "EX6", "response": "Yes", "remark": "OK"},
    {"section": "Excavation", "item_id": "EX7", "response": "Yes", "remark": "Restricted"},
    {"section": "Permits", "item_id": "PM1", "response": "Yes", "remark": "Valid"},
    {"section": "Permits", "item_id": "PM2", "response": "Yes", "remark": "Done"},
    {"section": "Permits", "item_id": "PM3", "response": "Yes", "remark": "Recorded"},
    {"section": "Permits", "item_id": "PM4", "response": "Yes", "remark": "Fulfilled"},
    {"section": "Permits", "item_id": "PM5", "response": "Yes", "remark": "Ensured"},
    {"section": "Permits", "item_id": "PM6", "response": "Yes", "remark": "Available"},
    {"section": "Permits", "item_id": "PM7", "response": "Yes", "remark": "Registered"},
    {"section": "Permits", "item_id": "PM8", "response": "Yes", "remark": "Retained"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG1",  "response": "Yes", "remark": "Outside"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG2",  "response": "Yes", "remark": "Secured"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG3",  "response": "Yes", "remark": "Checked"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG4",  "response": "Yes", "remark": "Kept away"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG5",  "response": "Yes", "remark": "Good"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG6",  "response": "Yes", "remark": "Separate"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG7",  "response": "Yes", "remark": "Coded"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG8",  "response": "Yes", "remark": "Used"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG9",  "response": "Yes", "remark": "Working"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG10", "response": "Yes", "remark": "Used"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG11", "response": "Yes", "remark": "Provided"},
    {"section": "Cutting_Welding_Grinding", "item_id": "WG12", "response": "Yes", "remark": "Installed"},
    {"section": "Abrasive_Blasting_Painting", "item_id": "AB1", "response": "Yes", "remark": "Approved"},
    {"section": "Abrasive_Blasting_Painting", "item_id": "AB2", "response": "Yes", "remark": "Away"},
    {"section": "Abrasive_Blasting_Painting", "item_id": "AB3", "response": "Yes", "remark": "Wearing"},
    {"section": "Abrasive_Blasting_Painting", "item_id": "AB4", "response": "Yes", "remark": "Adopted"},
    {"section": "Working_at_Heights", "item_id": "WH1", "response": "Yes", "remark": "Obtained"},
    {"section": "Working_at_Heights", "item_id": "WH2", "response": "Yes", "remark": "Used"},
    {"section": "Working_at_Heights", "item_id": "WH3", "response": "Yes", "remark": "Cordoned"},
    {"section": "Working_at_Heights", "item_id": "WH4", "response": "Yes", "remark": "Inspected"},
    {"section": "Working_at_Heights", "item_id": "WH5", "response": "Yes", "remark": "Provided"},
    {"section": "Confined_Space", "item_id": "CS1",  "response": "Yes", "remark": "Done"},
    {"section": "Confined_Space", "item_id": "CS2",  "response": "Yes", "remark": "Obtained"},
    {"section": "Confined_Space", "item_id": "CS3",  "response": "Yes", "remark": "Tested"},
    {"section": "Confined_Space", "item_id": "CS4",  "response": "Yes", "remark": "Ensured"},
    {"section": "Confined_Space", "item_id": "CS5",  "response": "Yes", "remark": "Available"},
    {"section": "Confined_Space", "item_id": "CS6",  "response": "Yes", "remark": "Provided"},
    {"section": "Confined_Space", "item_id": "CS7",  "response": "Yes", "remark": "Used"},
    {"section": "Confined_Space", "item_id": "CS8",  "response": "Yes", "remark": "Stationed"},
    {"section": "Confined_Space", "item_id": "CS9",  "response": "Yes", "remark": "Available"},
    {"section": "Confined_Space", "item_id": "CS10", "response": "Yes", "remark": "Trained"},
    {"section": "Material_Handling_Lifting", "item_id": "MH1", "response": "Yes", "remark": "Tested"},
    {"section": "Material_Handling_Lifting", "item_id": "MH2", "response": "Yes", "remark": "Inspected"},
    {"section": "Material_Handling_Lifting", "item_id": "MH3", "response": "Yes", "remark": "Available"},
    {"section": "Material_Handling_Lifting", "item_id": "MH4", "response": "Yes", "remark": "Prepared"},
    {"section": "Electrical_Safety", "item_id": "EL1",  "response": "Yes", "remark": "Followed"},
    {"section": "Electrical_Safety", "item_id": "EL2",  "response": "Yes", "remark": "Displayed"},
    {"section": "Electrical_Safety", "item_id": "EL3",  "response": "Yes", "remark": "Licensed"},
    {"section": "Electrical_Safety", "item_id": "EL4",  "response": "Yes", "remark": "Done"},
    {"section": "Electrical_Safety", "item_id": "EL5",  "response": "Yes", "remark": "Used"},
    {"section": "Electrical_Safety", "item_id": "EL6",  "response": "Yes", "remark": "Inspected"},
    {"section": "Electrical_Safety", "item_id": "EL7",  "response": "Yes", "remark": "Tested"},
    {"section": "Electrical_Safety", "item_id": "EL8",  "response": "Yes", "remark": "Insulated"},
    {"section": "Electrical_Safety", "item_id": "EL9",  "response": "Yes", "remark": "Used"},
    {"section": "Electrical_Safety", "item_id": "EL10", "response": "Yes", "remark": "Followed"},
    {"section": "Electrical_Safety", "item_id": "EL11", "response": "Yes", "remark": "Trained"},
    {"section": "Road_Work", "item_id": "RW1", "response": "Yes", "remark": "Barricaded"},
    {"section": "Road_Work", "item_id": "RW2", "response": "Yes", "remark": "Licensed"},
    {"section": "Formwork_Reinforcement", "item_id": "FW1", "response": "Yes", "remark": "Designed"},
    {"section": "Formwork_Reinforcement", "item_id": "FW2", "response": "Yes", "remark": "Using PPE"},
    {"section": "Concreting", "item_id": "CO1", "response": "Yes", "remark": "Barricaded"},
    {"section": "Concreting", "item_id": "CO2", "response": "Yes", "remark": "Provided"},
    {"section": "Demolishing", "item_id": "DM1", "response": "Yes", "remark": "Surveyed"},
    {"section": "Demolishing", "item_id": "DM2", "response": "Yes", "remark": "Isolated"},
    {"section": "Radiography", "item_id": "RA1", "response": "Yes", "remark": "As per AERB"},
    {"section": "Radiography", "item_id": "RA2", "response": "Yes", "remark": "Cordoned"},
    {"section": "Radiography", "item_id": "RA3", "response": "Yes", "remark": "Valid cert"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC1",  "response": "Yes", "remark": "Valid permit"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC2",  "response": "Yes", "remark": "Displayed"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC3",  "response": "Yes", "remark": "Approved"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC4",  "response": "Yes", "remark": "Removed"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC5",  "response": "Yes", "remark": "Shielded"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC6",  "response": "Yes", "remark": "Tested"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC7",  "response": "Yes", "remark": "Regular"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC8",  "response": "Yes", "remark": "Maintained"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC9",  "response": "Yes", "remark": "Clear"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC10", "response": "Yes", "remark": "Trained"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC11", "response": "Yes", "remark": "Audible"},
    {"section": "Hydrocarbon_Safety", "item_id": "HC12", "response": "Yes", "remark": "In place"},
    {"section": "Emergency_Procedures", "item_id": "EP1",  "response": "Yes", "remark": "Effective"},
    {"section": "Emergency_Procedures", "item_id": "EP2",  "response": "Yes", "remark": "Adequate"},
    {"section": "Emergency_Procedures", "item_id": "EP3",  "response": "Yes", "remark": "Installed"},
    {"section": "Emergency_Procedures", "item_id": "EP4",  "response": "Yes", "remark": "Clear"},
    {"section": "Emergency_Procedures", "item_id": "EP5",  "response": "Yes", "remark": "Adequate"},
    {"section": "Emergency_Procedures", "item_id": "EP6",  "response": "Yes", "remark": "Provided"},
    {"section": "Emergency_Procedures", "item_id": "EP7",  "response": "Yes", "remark": "Tie-up done"},
    {"section": "Emergency_Procedures", "item_id": "EP8",  "response": "Yes", "remark": "Earmarked"},
    {"section": "Emergency_Procedures", "item_id": "EP9",  "response": "Yes", "remark": "Trained"},
    {"section": "Emergency_Procedures", "item_id": "EP10", "response": "Yes", "remark": "Displayed"},
    {"section": "Emergency_Procedures", "item_id": "EP11", "response": "Yes", "remark": "Conducted"},
    {"section": "Welfare_Facilities", "item_id": "WF1", "response": "Yes", "remark": "Hygienic"},
    {"section": "Welfare_Facilities", "item_id": "WF2", "response": "Yes", "remark": "Available"},
    {"section": "Welfare_Facilities", "item_id": "WF3", "response": "Yes", "remark": "Proper"},
    {"section": "Welfare_Facilities", "item_id": "WF4", "response": "Yes", "remark": "Tie-up"},
    {"section": "Welfare_Facilities", "item_id": "WF5", "response": "Yes", "remark": "Available"},
    {"section": "Welfare_Facilities", "item_id": "WF6", "response": "Yes", "remark": "Provided"},
    {"section": "Welfare_Facilities", "item_id": "WF7", "response": "Yes", "remark": "Adequate"},
    {"section": "Welfare_Facilities", "item_id": "WF8", "response": "Yes", "remark": "Proper"},
    {"section": "General", "item_id": "GN1",  "response": "Yes", "remark": "Adequate"},
    {"section": "General", "item_id": "GN2",  "response": "Yes", "remark": "Adequate"},
    {"section": "General", "item_id": "GN3",  "response": "Yes", "remark": "Provided"},
    {"section": "General", "item_id": "GN4",  "response": "Yes", "remark": "Secured"},
    {"section": "General", "item_id": "GN5",  "response": "Yes", "remark": "Earthed"},
    {"section": "General", "item_id": "GN6",  "response": "Yes", "remark": "Checked"},
    {"section": "General", "item_id": "GN7",  "response": "Yes", "remark": "Used properly"},
    {"section": "General", "item_id": "GN8",  "response": "Yes", "remark": "Proper"},
    {"section": "General", "item_id": "GN9",  "response": "Yes", "remark": "Provided"},
    {"section": "General", "item_id": "GN10", "response": "Yes", "remark": "Installed"},
    {"section": "General", "item_id": "GN11", "response": "Yes", "remark": "Provided"},
    {"section": "General", "item_id": "GN12", "response": "Yes", "remark": "Certified"},
    {"section": "General", "item_id": "GN13", "response": "Yes", "remark": "Informed"},
    {"section": "Safety_Awareness_Training", "item_id": "SA1", "response": "Yes", "remark": "Conducted"},
    {"section": "Safety_Awareness_Training", "item_id": "SA2", "response": "Yes", "remark": "Conducted"},
    {"section": "Documentation", "item_id": "DC1", "response": "Yes", "remark": "System in place"},
    {"section": "Documentation", "item_id": "DC2", "response": "Yes", "remark": "Maintained"},
    {"section": "Documentation", "item_id": "DC3", "response": "Yes", "remark": "In place"},
    {"section": "Documentation", "item_id": "DC4", "response": "Yes", "remark": "Exists"},
]


def post(url, data, headers=None):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=h)
    return urllib.request.urlopen(req)


def get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return urllib.request.urlopen(req)


def login(username, password="demo1234"):
    body = urllib.parse.urlencode({"username": username, "password": password}).encode()
    res = urllib.request.urlopen(urllib.request.Request(f"{BASE}/auth/login", data=body))
    return json.loads(res.read())["access_token"]


def check(label, condition):
    if condition:
        print(f"  [OK]  {label}")
    else:
        print(f"  [FAIL] {label}")
        sys.exit(1)


print()
print("=== Smoke Test ===")

# Health
try:
    r = urllib.request.urlopen(f"{BASE}/health")
    h = json.loads(r.read())
    check("GET /health returns ok", h["status"] == "ok")
except Exception as e:
    print(f"  [FAIL] Server not responding: {e}")
    sys.exit(1)

# Inspector
tok_i = login("insp_off01")
ros = json.loads(get(f"{BASE}/my/ros", tok_i).read())
check("Inspector: GET /my/ros returns ROs", len(ros) >= 1)

ro_id = ros[0]["ro_id"]
res = json.loads(post(f"{BASE}/inspections", {"ro_id": ro_id, "items": ITEMS},
                      {"Authorization": f"Bearer {tok_i}"}).read())
check("Inspector: POST /inspections returns status=submitted", res.get("status") == "submitted")
insp_id = res["inspection_id"]

# Inspector cannot access zone_head endpoints
try:
    get(f"{BASE}/zone/inspections", tok_i)
    check("Inspector: blocked from /zone/inspections", False)
except urllib.error.HTTPError as e:
    check("Inspector: /zone/inspections returns 403", e.code == 403)

# Zone Head (Delhi NCR zone contains OFF01)
tok_z = login("zh_delhi_ncr")
zone_list = json.loads(get(f"{BASE}/zone/inspections", tok_z).read())
check("ZoneHead: /zone/inspections returns list", len(zone_list) >= 1)

detail = json.loads(get(f"{BASE}/inspections/{insp_id}", tok_z).read())
check("ZoneHead: /inspections/{id} returns items", len(detail["items"]) == 144)
check("ZoneHead: detail has dept breakdown", len(detail["department_risks"]) >= 1)
check("ZoneHead: section_flags present", "section_flags" in detail)

# Zone Head from UP cannot see OFF01 inspection
tok_z_up = login("zh_up")
try:
    get(f"{BASE}/inspections/{insp_id}", tok_z_up)
    check("ZoneHead UP: blocked from OFF01 inspection", False)
except urllib.error.HTTPError as e:
    check("ZoneHead UP: gets 403 for out-of-zone inspection", e.code == 403)

# Dept Officer
tok_d = login("dept_ppe_off01")
dept_list = json.loads(get(f"{BASE}/dept/inspections", tok_d).read())
check("DeptOfficer: /dept/inspections returns list", len(dept_list) >= 1)

dept_det = json.loads(get(f"{BASE}/dept/inspections/{insp_id}", tok_d).read())
check("DeptOfficer: dept detail department=PPE", dept_det["department"] == "PPE")
check("DeptOfficer: dept detail has items", len(dept_det["items"]) >= 1)
check("DeptOfficer: dept risk band present", dept_det["dept_risk"]["risk_band"] is not None)

# Dept officer from OFF08 cannot see OFF01 inspection
tok_d2 = login("dept_ppe_off08")
try:
    get(f"{BASE}/dept/inspections/{insp_id}", tok_d2)
    check("DeptOfficer OFF08: blocked from OFF01 inspection", False)
except urllib.error.HTTPError as e:
    check("DeptOfficer OFF08: gets 403 for out-of-office inspection", e.code == 403)

# Inspector cannot see other office's RO
tok_i2 = login("insp_off02")
ros2 = json.loads(get(f"{BASE}/my/ros", tok_i2).read())
try:
    other_ro = next(r for r in ros2 if r["ro_id"] not in [x["ro_id"] for x in ros])
    body = json.dumps({"ro_id": other_ro["ro_id"], "items": ITEMS}).encode()
    req = urllib.request.Request(f"{BASE}/inspections",
                                  data=body,
                                  headers={"Content-Type": "application/json",
                                           "Authorization": f"Bearer {tok_i}"})
    urllib.request.urlopen(req)
    check("Inspector: blocked from submitting for other office RO", False)
except StopIteration:
    pass  # no other-office ROs in list (expected)
except urllib.error.HTTPError as e:
    check("Inspector: 403 submitting for other office RO", e.code == 403)

print()
print("All checks passed!")
print()
