# tools/upload_data_or_file.py
from upload_data_or_file import main as upload_data_or_file_func

def upload_data_or_file(args, user_id):
    from shared.user_manager import extract_user_id
    import azure.functions as func
    import json
    class DummyReq:
        def __init__(self, args, user_id):
            self._args = args
            self._user_id = user_id
        def get_json(self):
            return {**self._args, "user_id": self._user_id}
        def __getitem__(self, key):
            return self._args[key]
    req = DummyReq(args, user_id)
    resp = upload_data_or_file_func(req)
    try:
        return json.loads(resp.get_body())
    except Exception:
        return resp.get_body()
