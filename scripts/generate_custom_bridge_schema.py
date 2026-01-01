import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend"))

from backend.custom_bridge import ACTION_HANDLERS

payload_examples = {
    "ensure_authorized": {"login_hint": "dokuczacz@gmail.com"},
    "gmail_list": {"max_results": 5},
    "gmail_send": {
        "to": ["dokuczacz@gmail.com"],
        "subject": "Hello from GPT",
        "body": "Friendly test message to confirm Gmail bridge works."
    },
    "gmail_get": {"message_id": "MESSAGE_ID"},
    "gmail_attachment": {"message_id": "MESSAGE_ID", "attachment_id": "ATTACHMENT_ID"},
    "oauth_status": {},
    "oauth_authorize": {"login_hint": "dokuczacz@gmail.com"},
    "oauth_exchange": {"code": "AUTH_CODE"}
}

schema = {
    "openapi": "3.1.0",
    "info": {
        "title": "OmniFlow Custom Gmail Bridge (generated)",
        "version": "1.0.0",
        "description": "Auto-generated schema reflecting ACTION_HANDLERS."
    },
    "servers": [
        {"url": "https://agentbackendservice-dfcpcudzeah4b6ae.northeurope-01.azurewebsites.net"}
    ],
    "components": {
        "securitySchemes": {
            "functionKey": {
                "type": "apiKey",
                "in": "header",
                "name": "x-functions-key",
                "description": "Function key sent via header."
            }
        },
        "schemas": {
            "Action": {
                "type": "string",
                "enum": list(ACTION_HANDLERS.keys())
            },
            "BridgeRequest": {
                "type": "object",
                "properties": {
                    "action": {"$ref": "#/components/schemas/Action"},
                    "user_id": {"type": "string"},
                    "payload": {"type": "object", "additionalProperties": True}
                },
                "required": ["action", "user_id"]
            }
        }
    },
    "security": [{"functionKey": []}],
    "paths": {
        "/api/custom_bridge": {
            "post": {
                "operationId": "custom_bridge",
                "summary": "Unified GPT tool for Gmail actions.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/BridgeRequest"},
                            "examples": {}
                        }
                    }
                },
                "responses": {
                    "200": {"description": "Successful action result."},
                    "400": {"description": "Missing payload or invalid action."},
                    "401": {"description": "Invalid function key."},
                    "500": {"description": "Server error."}
                }
            }
        }
    }
}

examples = schema["paths"]["/api/custom_bridge"]["post"]["requestBody"]["content"]["application/json"]["examples"]

for action in ACTION_HANDLERS:
    examples[action] = {
        "summary": f"{action} example",
        "value": {
            "action": action,
            "user_id": "dokuczacz@gmail.com",
            "payload": payload_examples.get(action, {})
        }
    }

output = Path("docs/shared/custom_bridge_generated_schema.json")
output.write_text(json.dumps(schema, indent=2))
print(f"Schema generated at {output.resolve()}")
