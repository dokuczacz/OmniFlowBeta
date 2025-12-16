import requests
import json

BASE_URL = "http://localhost:7071/api/add_new_data"
HEADERS = {
    "Content-Type": "application/json",
    "x-user-id": "testuser123"
}

def test_valid():
    payload = {
        "target_blob_name": "TM.json",
        "new_entry": {"test": "value1"}
    }
    resp = requests.post(BASE_URL, headers=HEADERS, data=json.dumps(payload))
    print("Valid request:", resp.status_code, resp.json())

def test_missing_user_id():
    payload = {
        "target_blob_name": "TM.json",
        "new_entry": {"test": "value2"}
    }
    resp = requests.post(BASE_URL, headers={"Content-Type": "application/json"}, data=json.dumps(payload))
    print("Missing user_id:", resp.status_code, resp.json())

def test_invalid_blob_name():
    payload = {
        "target_blob_name": "../hack.json",
        "new_entry": {"test": "value3"}
    }
    resp = requests.post(BASE_URL, headers=HEADERS, data=json.dumps(payload))
    print("Invalid blob name:", resp.status_code, resp.json())

def test_missing_fields():
    payload = {
        "target_blob_name": "TM.json"
        # missing new_entry
    }
    resp = requests.post(BASE_URL, headers=HEADERS, data=json.dumps(payload))
    print("Missing new_entry:", resp.status_code, resp.json())

if __name__ == "__main__":
    test_valid()
    test_missing_user_id()
    test_invalid_blob_name()
    test_missing_fields()
