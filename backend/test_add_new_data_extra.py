import requests
import json
import time

BASE_URL = "http://localhost:7071/api/add_new_data"
HEADERS = {
    "Content-Type": "application/json",
    "x-user-id": "testuser123"
}

# Test appending multiple entries and reading back

def test_append_multiple():
    print("\n--- test_append_multiple ---")
    for i in range(3):
        payload = {
            "target_blob_name": "TM.json",
            "new_entry": {"seq": i, "val": f"entry_{i}"}
        }
        resp = requests.post(BASE_URL, headers=HEADERS, data=json.dumps(payload))
        print(f"Append {i}: ", resp.status_code, resp.json())

# Test user isolation

def test_user_isolation():
    print("\n--- test_user_isolation ---")
    payload = {
        "target_blob_name": "TM.json",
        "new_entry": {"user": "A"}
    }
    respA = requests.post(BASE_URL, headers={**HEADERS, "x-user-id": "userA"}, data=json.dumps(payload))
    payload["new_entry"] = {"user": "B"}
    respB = requests.post(BASE_URL, headers={**HEADERS, "x-user-id": "userB"}, data=json.dumps(payload))
    print("User A:", respA.status_code, respA.json())
    print("User B:", respB.status_code, respB.json())

# Test invalid user_id (path traversal)
def test_invalid_user_id():
    print("\n--- test_invalid_user_id ---")
    payload = {
        "target_blob_name": "TM.json",
        "new_entry": {"test": "baduser"}
    }
    resp = requests.post(BASE_URL, headers={"Content-Type": "application/json", "x-user-id": "../hack"}, data=json.dumps(payload))
    print("Invalid user_id:", resp.status_code, resp.json())

# Test latency measurement (timing)
def test_latency():
    print("\n--- test_latency ---")
    payload = {
        "target_blob_name": "TM.json",
        "new_entry": {"test": "latency"}
    }
    start = time.time()
    resp = requests.post(BASE_URL, headers=HEADERS, data=json.dumps(payload))
    duration = (time.time() - start) * 1000
    print("Latency test:", resp.status_code, resp.json(), f"duration_ms={duration:.2f}")

if __name__ == "__main__":
    test_append_multiple()
    test_user_isolation()
    test_invalid_user_id()
    test_latency()
