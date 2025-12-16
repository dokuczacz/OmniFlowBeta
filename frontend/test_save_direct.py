import requests

url = "http://localhost:7071/api/save_interaction"
payload = {
    "user_message": "Test direct save",
    "assistant_response": "Direct save works!",
    "thread_id": "thread_direct",
    "user_id": "testuser"
}
headers = {"Content-Type": "application/json"}

response = requests.post(url, json=payload, headers=headers)
print("[Direct save_interaction] Status:", response.status_code)
print("[Direct save_interaction] Response:", response.text)
