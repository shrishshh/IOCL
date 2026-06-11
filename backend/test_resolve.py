import requests

BASE = "http://localhost:8000"

# Login as dept_ppe_off01
r = requests.post(f"{BASE}/auth/login", data={"username": "dept_ppe_off01", "password": "demo1234"})
tok = r.json()["access_token"]
hdr = {"Authorization": f"Bearer {tok}"}

inspections = requests.get(f"{BASE}/dept/inspections", headers=hdr).json()
print(f"Inspections: {len(inspections)}")
if not inspections:
    print("No inspections — submit one via the app first")
    raise SystemExit(0)

insp_id = inspections[0]["id"]
detail = requests.get(f"{BASE}/dept/inspections/{insp_id}", headers=hdr).json()
items = detail["items"]
print(f"PPE items: {len(items)}")

resolvable = [it for it in items if it["predicted_label"] in ("Medium", "High") and not it["resolved"]]
print(f"Resolvable (unresolved Med/High): {len(resolvable)}")

if resolvable:
    it = resolvable[0]
    item_db_id = it["id"]
    print(f"Resolving item db_id={item_db_id} item_id={it['item_id']} label={it['predicted_label']}")
    res = requests.post(f"{BASE}/dept/inspections/{insp_id}/items/{item_db_id}/resolve", headers=hdr)
    print(f"Status: {res.status_code}")
    body = res.json()
    print(f"resolved={body['resolved']}, by={body['resolved_by_name']}, at={body['resolved_at']}")

    # Zone head should see it resolved too
    zh_r = requests.post(f"{BASE}/auth/login", data={"username": "zh_delhi_ncr", "password": "demo1234"})
    zh_tok = zh_r.json()["access_token"]
    zh_hdr = {"Authorization": f"Bearer {zh_tok}"}
    zh_detail = requests.get(f"{BASE}/inspections/{insp_id}", headers=zh_hdr).json()
    zh_items = zh_detail["items"]
    matched = [i for i in zh_items if i["id"] == item_db_id]
    if matched:
        print(f"ZoneHead sees: resolved={matched[0]['resolved']}, by={matched[0]['resolved_by_name']}")
    else:
        print("WARNING: zone head detail missing the item")

    # Wrong dept officer should get 403
    r2 = requests.post(f"{BASE}/auth/login", data={"username": "dept_housekeeping_off01", "password": "demo1234"})
    tok2 = r2.json()["access_token"]
    hdr2 = {"Authorization": f"Bearer {tok2}"}
    bad = requests.post(f"{BASE}/dept/inspections/{insp_id}/items/{item_db_id}/resolve", headers=hdr2)
    print(f"Wrong dept officer resolve -> HTTP {bad.status_code} (expected 403)")

    # Idempotent re-resolve
    re_res = requests.post(f"{BASE}/dept/inspections/{insp_id}/items/{item_db_id}/resolve", headers=hdr)
    body2 = re_res.json()
    print(f"Idempotent re-resolve -> resolved={body2['resolved']}, by={body2['resolved_by_name']}")
else:
    print("No resolvable items in this inspection")
