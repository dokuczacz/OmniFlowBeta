# tools/update_data_entry.py
from update_data_entry import main as update_data_entry_func

def update_data_entry(args, user_id):
    from shared.user_manager import extract_user_id
    import azure.functions as func
    import json
    class DummyReq:
        def __init__(self, args, user_id):
            self._args = args or {}
            self._user_id = user_id
            self.headers = {"x-user-id": str(user_id)}
            self.params = dict(self._args)
        def get_json(self):
            return {**self._args, "user_id": self._user_id}
        def __getitem__(self, key):
            return self._args[key]
    req = DummyReq(args, user_id)
    resp = update_data_entry_func(req)
    try:
        return json.loads(resp.get_body())
    except Exception:
        return resp.get_body()
