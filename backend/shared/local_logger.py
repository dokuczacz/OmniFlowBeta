"""
Local file logging for backend debugging and development analysis.
Logs are written to backend_debug.log in project root for developer visibility.
"""
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
import logging


class LocalLogger:
    """Local file logger with rotation for debugging"""
    
    LOG_FILE = "backend_debug.log"
    MAX_SIZE_MB = 10
    KEEP_BACKUPS = 3
    
    @staticmethod
    def _get_log_path() -> str:
        """Get absolute path to log file in project root"""
        # Get project root (parent of shared/ folder)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        return os.path.join(project_root, LocalLogger.LOG_FILE)
    
    @staticmethod
    def _rotate_if_needed(log_path: str) -> None:
        """Rotate log file if it exceeds size limit"""
        try:
            if not os.path.exists(log_path):
                return
            
            size_mb = os.path.getsize(log_path) / (1024 * 1024)
            if size_mb > LocalLogger.MAX_SIZE_MB:
                # Rotate existing backups
                for i in range(LocalLogger.KEEP_BACKUPS - 1, 0, -1):
                    old_backup = f"{log_path}.{i}"
                    new_backup = f"{log_path}.{i + 1}"
                    if os.path.exists(old_backup):
                        if i + 1 <= LocalLogger.KEEP_BACKUPS:
                            os.rename(old_backup, new_backup)
                        else:
                            os.remove(old_backup)
                
                # Move current log to .1
                os.rename(log_path, f"{log_path}.1")
                logging.info(f"Rotated log file: {log_path} ({size_mb:.1f}MB)")
        except Exception as e:
            logging.warning(f"Failed to rotate log: {e}")
    
    @staticmethod
    def log_to_file(
        function_name: str,
        action: str,
        status: str = "success",
        user_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Write structured log entry to local file.
        
        Args:
            function_name: Name of Azure Function (e.g., "tool_call_handler")
            action: Action performed (e.g., "assistant_request", "tool_call", "response")
            status: Status of action ("success", "error", "warning")
            user_id: User ID (masked for privacy)
            duration_ms: Duration in milliseconds
            error: Error message if status is "error"
            metadata: Additional context (endpoint, thread_id, tool_name, etc.)
        """
        try:
            log_path = LocalLogger._get_log_path()
            LocalLogger._rotate_if_needed(log_path)
            
            # Mask user_id for privacy
            masked_user_id = None
            if user_id:
                masked_user_id = user_id[:4] + "***" if len(user_id) > 4 else "***"
            
            # Build log entry
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "function": function_name,
                "action": action,
                "status": status,
                "user_id": masked_user_id,
            }
            
            if duration_ms is not None:
                log_entry["duration_ms"] = round(duration_ms, 2)
            
            if error:
                log_entry["error"] = str(error)
            
            if metadata:
                log_entry["metadata"] = metadata
            
            # Write to file (append mode)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
                
        except Exception as e:
            # Don't let logging failures break the application
            logging.warning(f"Failed to write to local log: {e}")


def log_request_start(function_name: str, user_id: str, endpoint: Optional[str] = None) -> float:
    """
    Log request start and return start time for duration calculation.
    
    Args:
        function_name: Name of Azure Function
        user_id: User ID making the request
        endpoint: Optional endpoint or action being called
    
    Returns:
        Start time in seconds (for duration calculation)
    """
    import time
    start_time = time.time()
    
    metadata = {}
    if endpoint:
        metadata["endpoint"] = endpoint
    
    LocalLogger.log_to_file(
        function_name=function_name,
        action="request_start",
        status="info",
        user_id=user_id,
        metadata=metadata
    )
    
    return start_time


def log_request_end(
    function_name: str,
    start_time: float,
    user_id: str,
    status: str = "success",
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log request completion with duration.
    
    Args:
        function_name: Name of Azure Function
        start_time: Start time from log_request_start()
        user_id: User ID making the request
        status: Status of request ("success" or "error")
        error: Error message if failed
        metadata: Additional context
    """
    import time
    duration_ms = (time.time() - start_time) * 1000
    
    LocalLogger.log_to_file(
        function_name=function_name,
        action="request_end",
        status=status,
        user_id=user_id,
        duration_ms=duration_ms,
        error=error,
        metadata=metadata
    )


def log_tool_call(
    function_name: str,
    tool_name: str,
    user_id: str,
    duration_ms: Optional[float] = None,
    status: str = "success",
    error: Optional[str] = None
) -> None:
    """
    Log tool call execution.
    
    Args:
        function_name: Name of Azure Function (usually "tool_call_handler")
        tool_name: Name of tool being called
        user_id: User ID making the request
        duration_ms: Duration in milliseconds
        status: Status of tool call
        error: Error message if failed
    """
    LocalLogger.log_to_file(
        function_name=function_name,
        action="tool_call",
        status=status,
        user_id=user_id,
        duration_ms=duration_ms,
        error=error,
        metadata={"tool_name": tool_name}
    )


# Export main functions
__all__ = [
    "LocalLogger",
    "log_request_start",
    "log_request_end",
    "log_tool_call"
]
