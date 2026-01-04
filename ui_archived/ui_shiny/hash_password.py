from __future__ import annotations

import argparse
import base64
import hashlib
import os
import secrets


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str, *, iterations: int = 260_000, salt: bytes | None = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64(salt)}${_b64(dk)}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate UI_USERS_JSON hash entry (pbkdf2_sha256).")
    p.add_argument("--user", required=True, help="User id (key in UI_USERS_JSON).")
    p.add_argument("--password", required=True, help="Plain password to hash.")
    p.add_argument("--iterations", type=int, default=int(os.environ.get("UI_PBKDF2_ITERS", "260000")))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    hashed = hash_password(args.password, iterations=args.iterations)
    print(f"User: {args.user}")
    print(f"Hash: {hashed}")
    print("")
    print("Add to UI_USERS_JSON, e.g.:")
    print("{")
    print(f'  "{args.user}": "{hashed}"')
    print("}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

