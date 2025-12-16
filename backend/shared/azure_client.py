"""
Azure Blob Storage client factory with user isolation support
"""
import logging
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.core.exceptions import AzureError, ResourceNotFoundError
from typing import Optional, List

from .config import AzureConfig, UserNamespace


class AzureBlobClient:
    """Factory for Azure Blob Storage clients with user isolation"""
    
    _service_client: Optional[BlobServiceClient] = None
    _container_client: Optional[ContainerClient] = None
    
    @classmethod
    def get_service_client(cls) -> BlobServiceClient:
        """Get or create Azure Blob Service client (singleton pattern)"""
        if cls._service_client is None:
            try:
                cls._service_client = BlobServiceClient.from_connection_string(
                    AzureConfig.CONNECTION_STRING
                )
                logging.info("Azure Blob Service client initialized successfully")
            except AzureError as e:
                logging.error(f"Failed to initialize Blob Service client: {e}")
                raise
        
        return cls._service_client
    
    @classmethod
    def get_container_client(cls) -> ContainerClient:
        """Get or create container client (singleton pattern)"""
        if cls._container_client is None:
            service_client = cls.get_service_client()
            try:
                cls._container_client = service_client.get_container_client(
                    AzureConfig.CONTAINER_NAME
                )
                logging.info(f"Container client initialized for container: {AzureConfig.CONTAINER_NAME}")
            except AzureError as e:
                logging.error(f"Failed to initialize container client: {e}")
                raise
        
        return cls._container_client
    
    @classmethod
    def get_blob_client(
        cls, 
        blob_name: str, 
        user_id: Optional[str] = None
    ) -> BlobClient:
        """
        Get blob client with optional user isolation.
        
        Args:
            blob_name: Name of the blob file (e.g., "tasks.json")
            user_id: Optional user ID for namespace isolation
            
        Returns:
            BlobClient for the specified blob
        """
        # Apply user namespace if provided
        if user_id:
            blob_name = UserNamespace.get_user_blob_name(user_id, blob_name)
        
        container_client = cls.get_container_client()
        try:
            blob_client = container_client.get_blob_client(blob_name)
            logging.debug(f"Blob client retrieved for: {blob_name}")
            return blob_client
        except AzureError as e:
            logging.error(f"Failed to get blob client for {blob_name}: {e}")
            raise
    
    @classmethod
    def list_user_blobs(
        cls,
        user_id: str,
        prefix: Optional[str] = None
    ) -> List[str]:
        """
        List all blobs for a specific user.
        
        Args:
            user_id: User ID to filter by
            prefix: Optional prefix filter within user namespace (e.g., "tasks" to find "tasks*.json")
            
        Returns:
            List of blob names (without user prefix, just filenames)
        """
        container_client = cls.get_container_client()
        user_namespace_prefix = f"users{UserNamespace.USER_PREFIX_SEPARATOR}{user_id}{UserNamespace.USER_PREFIX_SEPARATOR}"
        
        if prefix:
            full_prefix = f"{user_namespace_prefix}{prefix}"
        else:
            full_prefix = user_namespace_prefix
        
        try:
            blobs = container_client.list_blobs(name_starts_with=full_prefix)
            
            # Extract just the filename (remove user namespace prefix)
            filenames = []
            for blob in blobs:
                filename = blob.name[len(user_namespace_prefix):]
                if filename:  # Skip empty names
                    filenames.append(filename)
            
            logging.info(f"Listed {len(filenames)} blobs for user {user_id}")
            return filenames
        except AzureError as e:
            logging.error(f"Failed to list blobs for user {user_id}: {e}")
            raise
    
    @classmethod
    def blob_exists(
        cls,
        blob_name: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Check if a blob exists.
        
        Args:
            blob_name: Name of the blob
            user_id: Optional user ID
            
        Returns:
            True if blob exists, False otherwise
        """
        try:
            blob_client = cls.get_blob_client(blob_name, user_id)
            blob_client.get_blob_properties()
            return True
        except ResourceNotFoundError:
            return False
        except AzureError as e:
            logging.warning(f"Error checking blob existence: {e}")
            return False


class AzureBlobError(Exception):
    """Custom exception for Azure Blob operations"""
    pass
