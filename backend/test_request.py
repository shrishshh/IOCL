"""
Quick smoke-test: post a sample inspection to /assess and print the response.
Run from the repo root:  python backend/test_request.py
(server must already be running on localhost:8000)
"""

import json
import urllib.request

PAYLOAD = {
    "inspection_id": "TEST001",
    "ro_name": "Patel Nagar RO",
    "items": [
        {
            "section": "Fire Safety",
            "item_id": "F1",
            "response": "Yes",
            "remark": "Fire extinguisher present but pressure critically low",
        },
        {
            "section": "Fire Safety",
            "item_id": "F2",
            "response": "No",
            "remark": "Emergency exit permanently blocked by LPG storage",
        },
        {
            "section": "Electrical",
            "item_id": "E1",
            "response": "Yes",
            "remark": "All electrical panels properly sealed and labelled",
        },
        {
            "section": "Electrical",
            "item_id": "E2",
            "response": "NA",
            "remark": "Underground cabling not applicable at this outlet",
        },
    ],
}

data = json.dumps(PAYLOAD).encode()
req = urllib.request.Request(
    "http://localhost:8000/assess",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read())

print(json.dumps(result, indent=2))
