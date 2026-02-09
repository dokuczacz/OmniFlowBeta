#!/usr/bin/env python3
"""
End-to-End Backend Test Script
Makes HTTP requests to local Azure Functions backend to test the full workflow.

Prerequisites:
- Backend running on http://localhost:7071
- OPENAI_API_KEY configured
- Azurite running

Usage:
    python test_e2e_backend.py [--base-url http://localhost:7071]
"""

import sys
import os
import json
import time
import requests
import argparse
from datetime import datetime

# Color output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BLUE}{'=' * 70}{Colors.END}")
    print(f"{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BLUE}{'=' * 70}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def print_info(text):
    print(f"ℹ️  {text}")

class E2ETestResults:
    def __init__(self):
        self.tests = []
        self.start_time = time.time()
    
    def add_result(self, test_name, passed, details=None, duration=None):
        self.tests.append({
            'name': test_name,
            'passed': passed,
            'details': details,
            'duration': duration
        })
        
        if passed:
            msg = f"PASS: {test_name}"
            if duration:
                msg += f" ({duration:.2f}s)"
            print_success(msg)
        else:
            print_error(f"FAIL: {test_name}")
        
        if details:
            print_info(f"  {details}")
    
    def summary(self):
        duration = time.time() - self.start_time
        passed = sum(1 for t in self.tests if t['passed'])
        failed = len(self.tests) - passed
        
        print_header("E2E TEST SUMMARY")
        print(f"Duration: {duration:.2f}s")
        print(f"Passed: {passed}/{len(self.tests)}")
        print(f"Failed: {failed}/{len(self.tests)}")
        
        if failed > 0:
            print("\nFailed Tests:")
            for test in self.tests:
                if not test['passed']:
                    print(f"  - {test['name']}")
                    if test['details']:
                        print(f"    {test['details']}")
        
        if failed == 0:
            print_success("\n🎉 ALL E2E TESTS PASSED!")
            return 0
        else:
            print_error(f"\n❌ {failed} E2E TEST(S) FAILED")
            return 1

def test_backend_health(base_url, results):
    """Test 1: Backend health check"""
    print_header("Test 1: Backend Health Check")
    
    start = time.time()
    try:
        # Try to connect to backend
        response = requests.get(f"{base_url}/api/get_current_time", timeout=5)
        duration = time.time() - start
        
        if response.status_code in [200, 401, 403]:  # Any response means backend is up
            results.add_result(
                "Backend health check",
                True,
                f"Backend responding (status: {response.status_code})",
                duration
            )
            return True
        else:
            results.add_result(
                "Backend health check",
                False,
                f"Unexpected status: {response.status_code}",
                duration
            )
            return False
    
    except requests.exceptions.ConnectionError:
        results.add_result(
            "Backend health check",
            False,
            f"Cannot connect to {base_url}. Is the backend running?"
        )
        return False
    except Exception as e:
        results.add_result(
            "Backend health check",
            False,
            str(e)
        )
        return False

def test_tool_call_handler_simple(base_url, results):
    """Test 2: Simple tool call (get_current_time)"""
    print_header("Test 2: Simple Tool Call - get_current_time")
    
    start = time.time()
    try:
        response = requests.post(
            f"{base_url}/api/tool_call_handler",
            json={
                "message": "What time is it?",
                "thread_id": "test-e2e-simple"
            },
            headers={
                "Content-Type": "application/json",
                "X-User-Id": "test-user-e2e"
            },
            timeout=30
        )
        duration = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            results.add_result(
                "Simple tool call (get_current_time)",
                True,
                f"Response received: {str(data)[:100]}...",
                duration
            )
            
            # Check for file handler usage in logs
            print_info("  Check backend_debug.log for 'tool_call_handler' entries")
            return True
        else:
            results.add_result(
                "Simple tool call (get_current_time)",
                False,
                f"Status: {response.status_code}, Body: {response.text[:200]}"
            )
            return False
    
    except Exception as e:
        results.add_result(
            "Simple tool call (get_current_time)",
            False,
            str(e)
        )
        return False

def test_tool_call_handler_complex(base_url, results):
    """Test 3: Complex query (should use DEEP mode)"""
    print_header("Test 3: Complex Tool Call - DEEP Mode")
    
    start = time.time()
    try:
        response = requests.post(
            f"{base_url}/api/tool_call_handler",
            json={
                "message": "Analyze my recent files, categorize them by topic, and provide a summary",
                "thread_id": "test-e2e-complex"
            },
            headers={
                "Content-Type": "application/json",
                "X-User-Id": "test-user-e2e"
            },
            timeout=60
        )
        duration = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            results.add_result(
                "Complex tool call (DEEP mode)",
                True,
                f"Response received in {duration:.2f}s",
                duration
            )
            return True
        else:
            results.add_result(
                "Complex tool call (DEEP mode)",
                False,
                f"Status: {response.status_code}"
            )
            return False
    
    except Exception as e:
        results.add_result(
            "Complex tool call (DEEP mode)",
            False,
            str(e)
        )
        return False

def test_error_handling(base_url, results):
    """Test 4: Error handling"""
    print_header("Test 4: Error Handling")
    
    start = time.time()
    try:
        # Send invalid request
        response = requests.post(
            f"{base_url}/api/tool_call_handler",
            json={
                "invalid_field": "test"
            },
            headers={
                "Content-Type": "application/json",
                "X-User-Id": "test-user-e2e"
            },
            timeout=30
        )
        duration = time.time() - start
        
        # We expect this to fail gracefully
        if response.status_code in [400, 500]:
            results.add_result(
                "Error handling (invalid request)",
                True,
                f"Backend returned error gracefully (status: {response.status_code})",
                duration
            )
            return True
        else:
            results.add_result(
                "Error handling (invalid request)",
                False,
                f"Unexpected status: {response.status_code}"
            )
            return False
    
    except Exception as e:
        results.add_result(
            "Error handling (invalid request)",
            False,
            str(e)
        )
        return False

def test_log_file_created(results):
    """Test 5: Verify log file was created"""
    print_header("Test 5: Log File Verification")
    
    log_file = "backend/backend_debug.log"
    
    if os.path.exists(log_file):
        size = os.path.getsize(log_file)
        results.add_result(
            "Log file created",
            True,
            f"backend_debug.log exists ({size} bytes)"
        )
        
        # Read and display recent entries
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                print_info(f"  Total log entries: {len(lines)}")
                
                # Show entries with 'tool_call_handler'
                handler_entries = [l for l in lines if 'tool_call_handler' in l]
                if handler_entries:
                    print_info(f"  Entries with 'tool_call_handler': {len(handler_entries)}")
                    print_info("  Latest entry:")
                    print_info(f"    {handler_entries[-1].strip()[:120]}...")
                else:
                    print_warning("  No entries with 'tool_call_handler' found yet")
        except Exception as e:
            print_warning(f"  Could not read log file: {e}")
        
        return True
    else:
        results.add_result(
            "Log file created",
            False,
            "backend_debug.log not found - file handler may not be working"
        )
        return False

def main():
    parser = argparse.ArgumentParser(description='E2E Backend Tests')
    parser.add_argument('--base-url', default='http://localhost:7071',
                       help='Base URL for backend (default: http://localhost:7071)')
    args = parser.parse_args()
    
    print_header("END-TO-END BACKEND TEST SUITE")
    print_info(f"Started at: {datetime.now().isoformat()}")
    print_info(f"Backend URL: {args.base_url}")
    
    results = E2ETestResults()
    
    # Run tests
    if not test_backend_health(args.base_url, results):
        print_error("\n❌ Backend not responding. Please start the backend first.")
        print_info("Run: cd backend && func start")
        return 1
    
    test_tool_call_handler_simple(args.base_url, results)
    test_tool_call_handler_complex(args.base_url, results)
    test_error_handling(args.base_url, results)
    test_log_file_created(results)
    
    return results.summary()

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
