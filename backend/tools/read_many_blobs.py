# tools/read_many_blobs.py
from read_many_blobs import main as read_many_blobs_func


def read_many_blobs(args, user_id):
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
    resp = read_many_blobs_func(req)
    try:
        return json.loads(resp.get_body())
    except Exception:
        return resp.get_body()

