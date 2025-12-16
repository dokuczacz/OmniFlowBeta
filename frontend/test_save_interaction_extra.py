import requests

url = "http://localhost:7071/api/save_interaction"
payload = {
    "user_message": "Hi",
    "assistant_response": "Hello!",
    "thread_id": "thread_123",
    "tool_calls": [{"tool_name": "add_new_data", "args": {"foo": "bar"}}],
    "metadata": {"source": "test_script", "extra": 42},
    "user_id": "alice",
    "custom_field": "should_be_ignored"
}
headers = {"Content-Type": "application/json"}

response = requests.post(url, json=payload, headers=headers)
print("Status:", response.status_code)
print("Response:", response.text)
