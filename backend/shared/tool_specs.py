"""
Tool specifications registry for OmniFlowBeta - Single source of truth for all tools.

This module defines TOOL_SPECS which contains canonical tool definitions including:
- Parameters (with types, required/optional, defaults)
- Parameter aliases (for backward compatibility)
- Descriptions and examples
- Validation rules

Based on patterns from OmniFlowCentral and AGENT_FUNCTIONS_CATALOG.json.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# Tool specifications - Single source of truth
TOOL_SPECS: Dict[str, Dict[str, Any]] = {
    "get_current_time": {
        "description": "Return current UTC time (ISO 8601). Use for stable IDs/timestamps and relative dates.",
        "method": "GET",
        "params": {},
        "aliases": {},
        "examples": [
            {
                "input": {},
                "output": {"status": "success", "time": "2026-02-05T21:00:00.000Z"}
            }
        ]
    },
    
    "list_blobs": {
        "description": "List files in the user's namespace. Optionally filter by prefix.",
        "method": "GET",
        "params": {
            "prefix": {
                "type": "str",
                "required": False,
                "default": "",
                "description": "Prefix inside user namespace"
            },
            "include_meta": {
                "type": "bool",
                "required": False,
                "default": False,
                "description": "If true, return name/size/last_modified in blobs_meta"
            }
        },
        "aliases": {},
        "examples": [
            {
                "input": {"prefix": "interactions/", "include_meta": True},
                "output": {"status": "success", "blobs": ["interactions/semantic/index.jsonl"], "count": 1}
            }
        ]
    },
    
    "read_blob_file": {
        "description": "Read a single blob file by name. Returns JSON if parseable, otherwise text.",
        "method": "GET",
        "params": {
            "file_name": {
                "type": "str",
                "required": True,
                "description": "Full path inside user namespace (e.g. TM.json, interactions/semantic/index.jsonl)"
            }
        },
        "aliases": {
            "target_blob_name": "file_name",
            "blob_name": "file_name",
            "name": "file_name"
        },
        "examples": [
            {
                "input": {"file_name": "TM.json"},
                "output": {"status": "success", "file_name": "TM.json", "data": {}}
            }
        ],
        "gotchas": [
            "If you pass only basename (e.g. index.jsonl) and it is nested, backend attempts unique suffix resolution",
            "If ambiguous, returns candidates[] array"
        ]
    },
    
    "read_many_blobs": {
        "description": "Read many blob files in one request with safety limits. Supports tail reads for text/JSONL.",
        "method": "POST",
        "params": {
            "files": {
                "type": "list",
                "required": True,
                "description": "Blob names relative to user namespace"
            },
            "tail_lines": {
                "type": "int",
                "required": False,
                "default": 0,
                "description": "If >0, return last N lines (best-effort) and do not parse JSON"
            },
            "tail_bytes": {
                "type": "int",
                "required": False,
                "default": 65536,
                "description": "Bytes from end when using tail_lines"
            },
            "max_bytes_per_file": {
                "type": "int",
                "required": False,
                "default": 262144,
                "description": "Prefix read limit per file (truncates larger files)"
            },
            "parse_json": {
                "type": "bool",
                "required": False,
                "default": True,
                "description": "Try JSON decode per file; fallback to text"
            }
        },
        "aliases": {},
        "examples": [
            {
                "input": {"files": ["TM.json", "LO.json"], "max_bytes_per_file": 262144},
                "output": {"status": "success", "count": 2, "items": []}
            }
        ]
    },
    
    "get_filtered_data": {
        "description": "Read a JSON file and optionally filter by a key/value on server-side (simple equality filter).",
        "method": "POST",
        "params": {
            "target_blob_name": {
                "type": "str",
                "required": True,
                "description": "Blob name to read and filter"
            },
            "filter_key": {
                "type": "str",
                "required": False,
                "description": "Key to filter on"
            },
            "filter_value": {
                "type": "str",
                "required": False,
                "description": "Value to match"
            }
        },
        "aliases": {
            "find_key": "filter_key",
            "find_value": "filter_value",
            "blob_name": "target_blob_name",
            "file_name": "target_blob_name"
        },
        "examples": [
            {
                "input": {"target_blob_name": "TM.json", "filter_key": "status", "filter_value": "todo"},
                "output": {"status": "success", "count": 5, "total": 10, "data": []}
            }
        ]
    },
    
    "add_new_data": {
        "description": "Add a new entry to a JSON array file. Creates file if it doesn't exist.",
        "method": "POST",
        "params": {
            "target_blob_name": {
                "type": "str",
                "required": True,
                "description": "JSON array file to add to"
            },
            "new_entry": {
                "type": "dict",
                "required": True,
                "description": "Entry to add (must be a dict)"
            }
        },
        "aliases": {
            "blob_name": "target_blob_name",
            "file_name": "target_blob_name"
        },
        "examples": [
            {
                "input": {"target_blob_name": "tasks.json", "new_entry": {"task": "Review code", "status": "pending"}},
                "output": {"status": "success", "count": 1}
            }
        ]
    },
    
    "update_data_entry": {
        "description": "Update an entry in a JSON array file by finding and modifying it.",
        "method": "POST",
        "params": {
            "target_blob_name": {
                "type": "str",
                "required": True,
                "description": "JSON array file to update"
            },
            "find_key": {
                "type": "str",
                "required": True,
                "description": "Key to find entry by"
            },
            "find_value": {
                "type": "str",
                "required": True,
                "description": "Value to match"
            },
            "update_key": {
                "type": "str",
                "required": True,
                "description": "Key to update"
            },
            "update_value": {
                "type": "any",
                "required": True,
                "description": "New value to set"
            }
        },
        "aliases": {
            "blob_name": "target_blob_name",
            "file_name": "target_blob_name"
        },
        "examples": [
            {
                "input": {
                    "target_blob_name": "tasks.json",
                    "find_key": "id",
                    "find_value": "123",
                    "update_key": "status",
                    "update_value": "completed"
                },
                "output": {"status": "success", "modified": 1}
            }
        ]
    },
    
    "remove_data_entry": {
        "description": "Remove an entry from a JSON array file by finding and deleting it.",
        "method": "POST",
        "params": {
            "target_blob_name": {
                "type": "str",
                "required": True,
                "description": "JSON array file to remove from"
            },
            "remove_key": {
                "type": "str",
                "required": True,
                "description": "Key to find entry by"
            },
            "remove_value": {
                "type": "str",
                "required": True,
                "description": "Value to match for removal"
            }
        },
        "aliases": {
            "blob_name": "target_blob_name",
            "file_name": "target_blob_name",
            "find_key": "remove_key",
            "find_value": "remove_value"
        },
        "examples": [
            {
                "input": {"target_blob_name": "tasks.json", "remove_key": "id", "remove_value": "123"},
                "output": {"status": "success", "removed": 1}
            }
        ]
    },
    
    "upload_data_or_file": {
        "description": "Upload/overwrite a blob file with content (JSON or text).",
        "method": "POST",
        "params": {
            "target_blob_name": {
                "type": "str",
                "required": True,
                "description": "Blob name to upload to"
            },
            "file_content": {
                "type": "any",
                "required": True,
                "description": "Content to upload (dict, list, or string)"
            },
            "overwrite": {
                "type": "bool",
                "required": False,
                "default": True,
                "description": "Whether to overwrite existing file"
            }
        },
        "aliases": {
            "blob_name": "target_blob_name",
            "file_name": "target_blob_name",
            "content": "file_content",
            "data": "file_content"
        },
        "examples": [
            {
                "input": {"target_blob_name": "notes.txt", "file_content": "My notes"},
                "output": {"status": "success", "uploaded": "notes.txt"}
            }
        ]
    },
    
    "manage_files": {
        "description": "Manage files (rename or delete operations).",
        "method": "POST",
        "params": {
            "operation": {
                "type": "str",
                "required": True,
                "description": "Operation to perform: 'rename' or 'delete'",
                "allowed_values": ["rename", "delete"]
            },
            "source_name": {
                "type": "str",
                "required": True,
                "description": "Source file name"
            },
            "target_name": {
                "type": "str",
                "required": False,
                "description": "Target file name (required for rename)"
            }
        },
        "aliases": {
            "source_blob_name": "source_name",
            "target_blob_name": "target_name"
        },
        "examples": [
            {
                "input": {"operation": "rename", "source_name": "old.json", "target_name": "new.json"},
                "output": {"status": "success", "operation": "rename"}
            },
            {
                "input": {"operation": "delete", "source_name": "temp.json"},
                "output": {"status": "success", "operation": "delete"}
            }
        ]
    },
    
    "save_interaction": {
        "description": "Save an interaction (user message + assistant response) to interaction log.",
        "method": "POST",
        "params": {
            "user_message": {
                "type": "str",
                "required": True,
                "description": "User's message"
            },
            "assistant_response": {
                "type": "str",
                "required": True,
                "description": "Assistant's response"
            },
            "metadata": {
                "type": "dict",
                "required": False,
                "description": "Optional metadata (thread_id, timestamp, etc.)"
            }
        },
        "aliases": {},
        "examples": [
            {
                "input": {
                    "user_message": "What is the weather?",
                    "assistant_response": "I don't have weather data.",
                    "metadata": {"thread_id": "thread-123"}
                },
                "output": {"status": "success", "saved": True}
            }
        ]
    },
    
    "get_interaction_history": {
        "description": "Retrieve interaction history with optional filtering.",
        "method": "GET",
        "params": {
            "limit": {
                "type": "int",
                "required": False,
                "default": 10,
                "description": "Maximum number of interactions to return"
            },
            "thread_id": {
                "type": "str",
                "required": False,
                "description": "Filter by thread_id"
            }
        },
        "aliases": {},
        "examples": [
            {
                "input": {"limit": 5, "thread_id": "thread-123"},
                "output": {"status": "success", "interactions": [], "count": 0}
            }
        ]
    },
    
    "custom_gpt_tools": {
        "description": "Execute custom GPT tool (passthrough to custom_gpt_tools endpoint).",
        "method": "POST",
        "params": {
            "action": {
                "type": "str",
                "required": True,
                "description": "Custom action to execute"
            },
            "params": {
                "type": "dict",
                "required": False,
                "description": "Parameters for the custom action"
            }
        },
        "aliases": {},
        "examples": [
            {
                "input": {"action": "custom_action", "params": {}},
                "output": {"status": "success"}
            }
        ]
    }
}


def get_tool_names() -> List[str]:
    """
    Get list of all canonical tool names.
    
    Returns:
        List of tool names
        
    Example:
        >>> tools = get_tool_names()
        >>> "read_blob_file" in tools
        True
    """
    return list(TOOL_SPECS.keys())


def get_tool_spec(tool_name: str) -> Optional[Dict[str, Any]]:
    """
    Get specification for a specific tool.
    
    Args:
        tool_name: Canonical tool name
        
    Returns:
        Tool specification dict or None if not found
        
    Example:
        >>> spec = get_tool_spec("read_blob_file")
        >>> spec["params"]["file_name"]["required"]
        True
    """
    return TOOL_SPECS.get(tool_name)


def tool_exists(tool_name: str) -> bool:
    """
    Check if a tool exists in the registry.
    
    Args:
        tool_name: Tool name to check
        
    Returns:
        True if tool exists, False otherwise
        
    Example:
        >>> tool_exists("read_blob_file")
        True
        >>> tool_exists("nonexistent_tool")
        False
    """
    return tool_name in TOOL_SPECS
