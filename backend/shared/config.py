"""
Configuration and environment management with user isolation support
"""
import os
from typing import Optional


class AzureConfig:
    """Centralized Azure configuration"""
    
    CONNECTION_STRING = os.environ.get(
        "AZURE_STORAGE_CONNECTION_STRING",
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;TableEndpoint=http://127.0.0.1:10002/devstoreaccount1"
    )
    
    CONTAINER_NAME = os.environ.get(
        "AZURE_BLOB_CONTAINER_NAME",
        "agent-knowledge-base"
    )
    
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    
    PROXY_URL = os.environ.get("PROXY_URL", "")


class UserNamespace:
    """User data namespace management"""
    
    DEFAULT_USER_ID = "default"
    USER_PREFIX_SEPARATOR = "/"
    
    @staticmethod
    def get_user_blob_name(user_id: str, file_name: str) -> str:
        """
        Generate user-namespaced blob name.
        
        Example: get_user_blob_name("user_123", "tasks.json") 
                 → "users/user_123/tasks.json"
        
        Args:
            user_id: Unique user identifier
            file_name: Original blob/file name (e.g., "tasks.json", "ideas.json")
            
        Returns:
            Namespaced blob name: "users/{user_id}/{file_name}"
        """
        if not user_id or user_id.isspace():
            user_id = UserNamespace.DEFAULT_USER_ID
        
        # Sanitize user_id - remove problematic characters
        user_id = user_id.replace("/", "_").replace("\\", "_").strip()
        
        return f"users{UserNamespace.USER_PREFIX_SEPARATOR}{user_id}{UserNamespace.USER_PREFIX_SEPARATOR}{file_name}"
    
    @staticmethod
    def extract_user_id_from_blob_name(blob_name: str) -> Optional[str]:
        """
        Extract user_id from namespaced blob name.
        
        Example: "users/user_123/tasks.json" → "user_123"
        
        Args:
            blob_name: Full namespaced blob name
            
        Returns:
            User ID or None if not in expected format
        """
        parts = blob_name.split(UserNamespace.USER_PREFIX_SEPARATOR)
        if len(parts) >= 3 and parts[0] == "users":
            return parts[1]
        return None
    
    @staticmethod
    def is_user_blob(blob_name: str) -> bool:
        """Check if blob follows user namespace convention"""
        return blob_name.startswith(f"users{UserNamespace.USER_PREFIX_SEPARATOR}")
