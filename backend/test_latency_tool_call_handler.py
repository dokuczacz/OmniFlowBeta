import requests
import time

BACKEND_URL = "http://localhost:7071/api/tool_call_handler"
USER_ID = "latency_test_user"

payload = {
    "message": "What time is it?",
    "user_id": USER_ID
}
headers = {"Content-Type": "application/json", "X-User-Id": USER_ID}

print("[TEST] Sending tool_call_handler request...")
t0 = time.time()
response = requests.post(BACKEND_URL, json=payload, headers=headers, timeout=30)
t1 = time.time()

print(f"[TEST] Status: {response.status_code}")
print(f"[TEST] Response: {response.text}")
print(f"[TEST] Latency: {t1-t0:.2f} seconds")
