"""
Centralized logging setup for the OmniFlow Azure Functions backend.

Goal (local dev + prod):
- Keep our own 1-line function logs readable.
- Suppress noisy Azure SDK HTTP request/response dumps unless explicitly enabled.
"""

from __future__ import annotations

import logging
import os


def _level_from_env(name: str, default: str) -> int:
    raw = str(os.environ.get(name) or default).strip().upper()
    return getattr(logging, raw, logging.WARNING)


def configure_azure_sdk_logging() -> None:
    """
    Configure Azure SDK related loggers.

    - Default: WARNING to avoid verbose HTTP dumps (Request URL/headers/etc.).
    - You can override via env:
        - AZURE_SDK_LOG_LEVEL=INFO|WARNING|ERROR|DEBUG
        - AZURE_HTTP_LOGGING=1 to re-enable HTTP logging policy
    """
    level = _level_from_env("AZURE_SDK_LOG_LEVEL", "WARNING")
    for logger_name in (
        "azure",
        "azure.core",
        "azure.storage",
        "azure.storage.blob",
        "azure.core.pipeline",
        "azure.core.pipeline.policies",
        "azure.core.pipeline.policies.http_logging_policy",
    ):
        logging.getLogger(logger_name).setLevel(level)

    http_logging_enabled = str(os.environ.get("AZURE_HTTP_LOGGING") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )
    if not http_logging_enabled:
        logging.getLogger("azure.core.pipeline.policies.http_logging_policy").disabled = True

