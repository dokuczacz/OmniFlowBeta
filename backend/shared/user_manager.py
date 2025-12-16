"""
User management and authentication utilities
"""
import logging
from typing import Optional, Tuple
import azure.functions as func


class UserValidator:
    """Validate and extract user information from requests"""
    
    # Priority order for user ID extraction
    USER_ID_SOURCES = [
        "user_id",      # HTTP header: X-User-Id
        "x_user_id",    # Alt header: X-User-Id (normalized)
        "userId",       # Query/body parameter: userId
        "user-id",      # Query/body parameter: user-id
    ]
    
    @staticmethod
    def get_user_id_from_request(req: func.HttpRequest) -> Tuple[str, bool]:
        """
        Extract user ID from HTTP request.
        
        Checks in order:
        1. HTTP header 'X-User-Id'
        2. Query parameter 'user_id' or 'userId'
        3. Request body JSON field 'user_id' or 'userId'
        
        Args:
            req: Azure Functions HTTP request
            
        Returns:
            Tuple of (user_id: str, is_valid: bool)
            Returns ("default", False) if no user ID found
        """
        # 1. Check HTTP headers
        user_id = req.headers.get("X-User-Id")
        if user_id and user_id.strip():
            logging.info(f"User ID extracted from header: {user_id}")
            return user_id.strip(), True
        
        # 2. Check query parameters
        user_id = req.params.get("user_id") or req.params.get("userId")
        if user_id and user_id.strip():
            logging.info(f"User ID extracted from query parameter: {user_id}")
            return user_id.strip(), True
        
        # 3. Check request body (JSON)
        try:
            body = req.get_json()
            if isinstance(body, dict):
                user_id = body.get("user_id") or body.get("userId")
                if user_id and str(user_id).strip():
                    logging.info(f"User ID extracted from request body: {user_id}")
                    return str(user_id).strip(), True
        except (ValueError, AttributeError):
            pass
        
        logging.warning("No user ID provided in request, using 'default'")
        return "default", False
    
    @staticmethod
    def validate_user_id(user_id: str) -> bool:
        """
        Validate user ID format.
        
        Rules:
        - Not empty or whitespace
        - Reasonable length (3-64 characters)
        - Alphanumeric, underscore, hyphen, dot allowed
        
        Args:
            user_id: User ID to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not user_id or not user_id.strip():
            return False
        
        user_id = user_id.strip()
        
        # Check length
        if len(user_id) < 3 or len(user_id) > 64:
            return False
        
        # Allow alphanumeric, underscore, hyphen, dot
        import re
        if not re.match(r'^[a-zA-Z0-9._-]+$', user_id):
            return False
        
        return True


class UserAuthorization:
    """User authorization and access control"""
    
    @staticmethod
    def check_user_access(req: func.HttpRequest, resource_user_id: str) -> bool:
        """
        Verify if request is authorized to access resource owned by resource_user_id.
        
        Basic implementation: requester must be the resource owner or "admin" role.
        
        Args:
            req: HTTP request
            resource_user_id: User ID of resource owner
            
        Returns:
            True if authorized, False otherwise
        """
        requester_id, _ = UserValidator.get_user_id_from_request(req)
        
        # Admin bypass
        admin_token = req.headers.get("X-Admin-Token")
        if admin_token == "admin":  # TODO: validate proper admin token
            return True
        
        # Owner access
        if requester_id == resource_user_id:
            return True
        
        return False


def extract_user_id(req: func.HttpRequest) -> str:
    """
    Convenience function to extract user ID from request.
    
    Args:
        req: HTTP request
        
    Returns:
        User ID (string)
    """
    user_id, _ = UserValidator.get_user_id_from_request(req)
    return user_id
