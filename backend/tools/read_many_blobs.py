# tools/read_many_blobs.py
from read_many_blobs.service import read_many_blobs_core


def read_many_blobs(args, user_id):
    files = args.get("files") or args.get("file_names") or []
    params = {
        "files": files,
        "tail_lines": args.get("tail_lines"),
        "tail_bytes": args.get("tail_bytes"),
        "max_bytes_per_file": args.get("max_bytes_per_file"),
        "parse_json": args.get("parse_json"),
        "max_files": args.get("max_files"),
    }
    result, _ = read_many_blobs_core(user_id=user_id, **params, raise_on_error=False)
    return result

