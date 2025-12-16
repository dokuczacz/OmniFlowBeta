import requests

url = "http://localhost:7071/api/proxy_router"
payload = {
    "action": "save_interaction",
    "params": {
        "user_message": "Test via proxy",
        "assistant_response": "Proxy save works!",
        "thread_id": "thread_proxy",
        "user_id": "testuser"
    }
}
headers = {"Content-Type": "application/json"}

response = requests.post(url, json=payload, headers=headers)
print("[Proxy save_interaction] Status:", response.status_code)
print("[Proxy save_interaction] Response:", response.text)
