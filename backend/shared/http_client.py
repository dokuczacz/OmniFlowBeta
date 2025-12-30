import logging
from typing import Any, Dict, Optional

import requests


def _http_debug(code: str, *, user_id: str = "", thread_id: str = "", url: str = "", method: str = "", error: Exception | None = None) -> None:
    logger = logging.getLogger()
    if not logger.isEnabledFor(logging.DEBUG):
        return
    try:
        err = f"{type(error).__name__}: {error}" if error else ""
        logging.debug(
            f"[HTTP] code={code} method={method} url={url} user_id={user_id} thread_id={thread_id} error={err}".strip()
        )
    except Exception:
        return


def requests_get(
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Any = 10,
    user_id: str = "",
    thread_id: str = "",
    code: str = "http_get",
) -> requests.Response:
    try:
        return requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        _http_debug(code, user_id=str(user_id or ""), thread_id=str(thread_id or ""), url=str(url or ""), method="GET", error=exc)
        raise


def requests_post(
    url: str,
    *,
    json: Any = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Any = 10,
    user_id: str = "",
    thread_id: str = "",
    code: str = "http_post",
) -> requests.Response:
    try:
        return requests.post(url, json=json, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        _http_debug(code, user_id=str(user_id or ""), thread_id=str(thread_id or ""), url=str(url or ""), method="POST", error=exc)
        raise

