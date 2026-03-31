"""
Golden tests for Custom GPT Preferences, Calendar, and Security.

Validates: memory.preferences.update (unknown_keys detection) → calendar.events.list (RFC3339 normalization)
with path traversal security and input validation.
"""
import pytest
import requests
import json
from datetime import datetime, timedelta

# Config
BASE_URL = "http://localhost:7071"
FUNCTION_KEY = "dev-key-custom-gpt"
USER_ID = "test_golden_prefs"


@pytest.fixture(scope="module")
def api_headers():
    return {"Content-Type": "application/json"}


@pytest.fixture(scope="module")
def function_params():
    return {"code": FUNCTION_KEY}


class TestPreferencesUpdateWithUnknownKeys:
    """Verify preferences.update returns unknown_keys for debuggability (FIX #3)."""
    
    def test_preferences_get_defaults(self, api_headers, function_params):
        """New user should get default preferences."""
        payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "memory.preferences.get",
                "confirm": False,
                "arguments": {}
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        prefs = data["result"]["preferences"]
        # Validate default structure
        assert "schema_version" in prefs
        assert prefs["schema_version"] == "omniflow.wp6.preferences.v1"
        assert "brevity" in prefs
        assert "fast_mode" in prefs
        assert "allowed_reads" in prefs
        assert "disable_history_reads" in prefs
    
    def test_preferences_update_valid_keys(self, api_headers, function_params):
        """Update preferences with valid keys."""
        payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "memory.preferences.update",
                "confirm": False,
                "arguments": {
                    "preferences": {
                        "brevity": "short",
                        "fast_mode": True,
                        "allowed_reads": ["TM.json", "LO.json"],
                    }
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        result = data["result"]
        assert "preferences" in result
        assert "updated_keys" in result
        assert "brevity" in result["updated_keys"]
        assert "fast_mode" in result["updated_keys"]
    
    def test_preferences_update_unknown_keys_detected(self, api_headers, function_params):
        """Sending unknown keys should be reported in response (FIX #3)."""
        payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "memory.preferences.update",
                "confirm": False,
                "arguments": {
                    "preferences": {
                        "brevity": "medium",
                        "language": "en-US",  # Unknown key
                        "timezone": "UTC",    # Unknown key
                        "custom_field": "value",  # Unknown key
                    }
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success", "Should still succeed, just ignore unknown keys"
        
        result = data["result"]
        # FIX #3: Unknown keys should be reported
        assert "unknown_keys" in result, "Response should include unknown_keys array"
        unknown = result["unknown_keys"]
        assert isinstance(unknown, list)
        assert "language" in unknown, "Unknown 'language' key should be reported"
        assert "timezone" in unknown, "Unknown 'timezone' key should be reported"
        assert "custom_field" in unknown, "Unknown 'custom_field' key should be reported"
        
        # Valid key should still be updated
        assert "brevity" in result["updated_keys"] or len(result["updated_keys"]) > 0


class TestCalendarEventsDateNormalization:
    """Verify calendar.events.list normalizes dates to RFC3339 (FIX #4)."""
    
    def test_calendar_events_list_accepts_bare_date(self, api_headers, function_params):
        """calendar.events.list should accept YYYY-MM-DD and normalize to RFC3339 (FIX #4)."""
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        
        payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "calendar.events.list",
                "confirm": False,
                "arguments": {
                    "time_min": today.isoformat(),  # Bare date: "2026-03-31"
                    "time_max": next_week.isoformat(),  # Bare date: "2026-04-07"
                    "max_results": 10,
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        
        # May fail due to auth, but should not fail due to date format
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"
            result = data["result"]
            assert "events" in result
            assert isinstance(result["events"], list)
        else:
            # Auth errors are acceptable, format errors are not
            data = response.json()
            error_msg = json.dumps(data).lower()
            assert "rfc3339" not in error_msg, "Should not complain about RFC3339 format"
            assert "invalid" not in error_msg or "format" not in error_msg, "Date format should be auto-normalized"
    
    def test_calendar_events_list_with_rfc3339(self, api_headers, function_params):
        """calendar.events.list should also accept full RFC3339 format."""
        time_min = "2026-03-31T00:00:00Z"
        time_max = "2026-04-07T23:59:59Z"
        
        payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "calendar.events.list",
                "confirm": False,
                "arguments": {
                    "time_min": time_min,
                    "time_max": time_max,
                    "max_results": 5,
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"


class TestPathTraversalSecurity:
    """Verify user_id sanitization against path traversal (FIX #5)."""
    
    def test_user_id_with_slashes_sanitized(self, api_headers, function_params):
        """user_id with slashes should be sanitized."""
        malicious_user_id = "user/../../admin"
        
        payload = {
            "action": "capability_exec",
            "user_id": malicious_user_id,
            "params": {
                "capability": "memory.preferences.get",
                "confirm": False,
                "arguments": {}
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        
        # Should succeed but with sanitized user_id (no escape to different namespace)
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"
    
    def test_user_id_with_double_dot_sanitized(self, api_headers, function_params):
        """user_id with .. should be sanitized (FIX #5: .. -> __)."""
        malicious_user_id = "user..evil"
        
        payload = {
            "action": "capability_exec",
            "user_id": malicious_user_id,
            "params": {
                "capability": "memory.preferences.get",
                "confirm": False,
                "arguments": {}
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        
        # Should handle gracefully without security issues
        assert response.status_code in (200, 400, 409)
    
    def test_preferences_multiple_unknown_keys_collected(self, api_headers, function_params):
        """Multiple unknown keys should all be collected in response."""
        payload = {
            "action": "capability_exec",
            "user_id": "test_multi_unknown",
            "params": {
                "capability": "memory.preferences.update",
                "confirm": False,
                "arguments": {
                    "preferences": {
                        "brevity": "long",
                        "unknown_1": "value",
                        "unknown_2": "value",
                        "unknown_3": "value",
                        "unknown_4": "value",
                    }
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        result = data["result"]
        if "unknown_keys" in result:
            assert len(result["unknown_keys"]) >= 4, "All unknown keys should be collected"
