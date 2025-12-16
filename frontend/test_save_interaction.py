import requests

url = "http://localhost:7071/api/save_interaction"
payload = {
    "user_message": "Hi",
    "assistant_response": "Hello!"
}
headers = {"Content-Type": "application/json"}

response = requests.post(url, json=payload, headers=headers)
print("Status:", response.status_code)
print("Response:", response.text)
