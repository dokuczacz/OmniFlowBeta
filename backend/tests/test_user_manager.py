import unittest
from unittest.mock import Mock
import sys
import os

# Add parent directory to path to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.user_manager import UserValidator

class TestUserValidator(unittest.TestCase):
    """
    Unit tests for UserValidator class.
    Demonstrates 'Business Approach': Verifying logic before deployment.
    """

    def test_extract_user_id_from_header(self):
        """Test extracting user_id from X-User-Id header"""
        # Arrange
        mock_req = Mock()
        mock_req.headers = {"X-User-Id": "test_user_123"}
        mock_req.params = {}
        
        # Act
        user_id, is_valid = UserValidator.get_user_id_from_request(mock_req)
        
        # Assert
        self.assertTrue(is_valid)
        self.assertEqual(user_id, "test_user_123")

    def test_extract_user_id_from_query(self):
        """Test extracting user_id from query parameters"""
        # Arrange
        mock_req = Mock()
        mock_req.headers = {}
        mock_req.params = {"user_id": "query_user_456"}
        
        # Act
        user_id, is_valid = UserValidator.get_user_id_from_request(mock_req)
        
        # Assert
        self.assertTrue(is_valid)
        self.assertEqual(user_id, "query_user_456")

    def test_extract_user_id_missing(self):
        """Test behavior when no user_id is provided"""
        # Arrange
        mock_req = Mock()
        mock_req.headers = {}
        mock_req.params = {}
        # Mock get_json to raise ValueError (simulating empty body)
        mock_req.get_json.side_effect = ValueError
        
        # Act
        user_id, is_valid = UserValidator.get_user_id_from_request(mock_req)
        
        # Assert
        self.assertFalse(is_valid)
        self.assertEqual(user_id, "default")

if __name__ == '__main__':
    unittest.main()
