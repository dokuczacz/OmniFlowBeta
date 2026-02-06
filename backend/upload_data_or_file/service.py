import json
import logging
from typing import Any, Dict, Tuple

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings

from shared.config import AzureConfig
from shared.manifest_helper import build_manifest_entry, upsert_manifest_entry


def _get_client():
    connection_string = AzureConfig.CONNECTION_STRING
    container_name = AzureConfig.CONTAINER_NAME
    if not connection_string or not container_name:
        raise RuntimeError('Missing Azure Storage configuration.')
    service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = service_client.get_container_client(container_name)
    return service_client, container_client


def _serialize_content(value: Any) -> Tuple[bytes, str]:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, indent=2)
        content_type = 'application/json'
    else:
        text = str(value)
        content_type = 'text/plain'
    payload = text.encode('utf-8')
    return payload, content_type


def upload_data_or_file_core(
    user_id: str,
    target_blob_name: str,
    file_content: Any,
    raise_on_error: bool = True,
) -> Tuple[Dict[str, Any], int]:
    if not target_blob_name:
        payload = {'status': 'error', 'error': "Missing required field 'target_blob_name'"}
        return payload, 400
    payload_bytes, content_type = _serialize_content(file_content)
    try:
        service_client, container_client = _get_client()
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.info('upload_data_or_file: container missing, creating')
            try:
                service_client.create_container(container_client.container_name)
            except AzureError:
                pass
            _, container_client = _get_client()

        namespaced = f"users/{user_id}/{target_blob_name.lstrip('/')}"
        blob_client = container_client.get_blob_client(namespaced)
        blob_client.upload_blob(payload_bytes, overwrite=True, content_settings=ContentSettings(content_type=content_type))
        response = {
            'status': 'success',
            'user_id': user_id,
            'blob_name': target_blob_name,
            'storage_location': namespaced,
            'content_type': content_type,
            'size_bytes': len(payload_bytes),
        }
        try:
            entry = build_manifest_entry(
                namespaced=namespaced,
                target_blob_name=target_blob_name,
                payload={'target_blob_name': target_blob_name},
                content_type=content_type,
                size=len(payload_bytes),
            )
            upsert_manifest_entry(container_client, user_id, entry)
            response['manifest_status'] = 'updated'
        except Exception as exc:
            logging.warning('upload_data_or_file: manifest update failed: %s', exc)
            response['manifest_status'] = 'failed'
            response['manifest_error'] = str(exc)
        return response, 200
    except AzureError as exc:
        logging.error('upload_data_or_file: azure error %s', exc)
        payload = {'status': 'error', 'user_id': user_id, 'error': f'Azure error: {exc}'}
        if raise_on_error:
            raise
        return payload, 500
    except Exception as exc:
        logging.exception('upload_data_or_file: unexpected error')
        payload = {'status': 'error', 'user_id': user_id, 'error': str(exc)}
        if raise_on_error:
            raise
        return payload, 500
