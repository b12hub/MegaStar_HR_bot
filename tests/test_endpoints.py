import requests
import time

BASE_URL = "http://127.0.0.1:8000"

# Adjust these IDs to match existing records in your DB if needed
VACANCY_ID = 2
CANDIDATE_ID =11
BRANCH_ID = 1

endpoints = [
    # --- HR Portal ---
    {
        "method": "POST",
        "path": "/hr/vacancies/create",
        "json": {
            "title": "Test AI Eng",
            "department": "Tech",
            "description": "Test",
            "branch_id": BRANCH_ID
        }
    },

    # --- Candidate Portal ---
    {"method": "GET", "path": "/apply/data"},
    {"method": "GET", "path": "/apply/portal"},
    {"method": "GET", "path": f"/apply/{VACANCY_ID}"},
    {
        "method": "POST",
        "path": f"/apply/{VACANCY_ID}",
        "data": {
            "full_name": "Test User",
            "phone_number": "998901234567"
        }
    },
    {
        "method": "POST",
        "path": "/apply/submit",
        "json": {
            "candidate_id": CANDIDATE_ID,
            "full_name": "Test Candidate",
            "phone_number": "+998901234567",
            "vacancy_id": VACANCY_ID,
            "branch_id": BRANCH_ID,
            "answers": {}
        }
    },

    # --- Dashboard ---
    {"method": "GET", "path": "/dashboard/hr"},
    {"method": "GET", "path": "/dashboard/vacancies/new"},
    {
        "method": "POST",
        "path": "/dashboard/vacancies/new",
        "data": {
            "title": "Dev",
            "department": "IT",
            "description": "FastAPI",
            "branch_id": BRANCH_ID
        }
    },
    {"method": "GET", "path": f"/dashboard/vacancies/{VACANCY_ID}"},
    {"method": "GET", "path": f"/dashboard/vacancies/{VACANCY_ID}/candidates"},
    {"method": "GET", "path": f"/dashboard/candidates/{CANDIDATE_ID}"},
    {
        "method": "POST",
        "path": f"/dashboard/candidates/{CANDIDATE_ID}/evaluate",
        "headers": {"Accept": "application/json"}
    },
    {"method": "POST", "path": f"/dashboard/vacancies/{VACANCY_ID}/toggle"},
    {"method": "GET", "path": f"/dashboard/vacancies/{VACANCY_ID}/edit"},
    {
        "method": "POST",
        "path": f"/dashboard/vacancies/{VACANCY_ID}/edit",
        "data": {
            "title": "Dev",
            "department": "IT",
            "description": "FastAPI",
            "branch_id": BRANCH_ID,
            "is_active": True
        }
    },
]

print(f"🚀 Pinging {len(endpoints)} endpoints on {BASE_URL}...\n")

for ep in endpoints:
    url = BASE_URL + ep["path"]
    method = ep["method"]

    kwargs = {}
    if "json" in ep: kwargs["json"] = ep["json"]
    if "data" in ep: kwargs["data"] = ep["data"]
    if "headers" in ep: kwargs["headers"] = ep["headers"]

    try:
        response = requests.request(method, url, allow_redirects=False, timeout=5, **kwargs)
        status = response.status_code

        if 200 <= status < 300:
            color = '\033[92m'  # Green
        elif 300 <= status < 400:
            color = '\033[93m'  # Yellow (Redirect)
        elif 400 <= status < 500:
            color = '\033[91m'  # Red
        else:
            color = '\033[95m'  # Magenta (500 Internal Error)

        reset = '\033[0m'
        print(f"[{color}{status}{reset}] {method.ljust(5)} {ep['path']}")

        if status in [422, 500]:
            print(f"      \033[90m↳ Detail: {response.text[:200]}\033[0m")

    except Exception as e:
        print(f"[\033[91mERR\033[0m]  {method.ljust(5)} {ep['path']} -> {str(e)}")

    time.sleep(0.1)

print("\n✅ Endpoint testing complete.")