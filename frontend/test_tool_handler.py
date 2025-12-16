import requests

url = "http://localhost:7071/api/tool_call_handler"
payload = {
    "message": "Test via tool handler",
    "user_id": "testuser"
}
headers = {"Content-Type": "application/json"}

response = requests.post(url, json=payload, headers=headers)
print("[Tool handler] Status:", response.status_code)
print("[Tool handler] Response:", response.text)
