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


def _serialize_json(value: Any) -> Tuple[bytes, str]:
    text = json.dumps(value, indent=2, ensure_ascii=False)
    return text.encode('utf-8'), 'application/json'


def add_new_data_core(user_id: str, target_blob_name: str, new_entry: Any, raise_on_error: bool = True) -> Tuple[Dict[str, Any], int]:
    if not target_blob_name:
        return ({'status':'error','error':"Missing target_blob_name"},400)
    payload_entry = new_entry
    if isinstance(new_entry, str):
        try:
            payload_entry = json.loads(new_entry)
        except Exception:
            payload_entry = {'_raw': new_entry}
    try:
        service_client, container_client = _get_client()
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.info('add_new_data: creating container')
            try:
                service_client.create_container(container_client.container_name)
            except AzureError:
                pass
            _, container_client = _get_client()
        namespaced = f"users/{user_id}/{target_blob_name.lstrip('/')}"
        blob_client = container_client.get_blob_client(namespaced)
        try:
            existing = blob_client.download_blob().readall().decode('utf-8')
            records = json.loads(existing)
        except ResourceNotFoundError:
            records = []
        except json.JSONDecodeError:
            records = []
        if not isinstance(records, list):
            records = [records]
        records.append(payload_entry)
        payload_bytes, content_type = _serialize_json(records)
        blob_client.upload_blob(payload_bytes, overwrite=True, content_settings=ContentSettings(content_type=content_type))
        response = {
            'status': 'success',
            'entry_count': len(records),
            'user_id': user_id,
        }
        try:
            entry = build_manifest_entry(
                namespaced=namespaced,
                target_blob_name=target_blob_name,
                payload={'target_blob_name': target_blob_name, 'new_entry': payload_entry},
                content_type='application/json',
                size=len(payload_bytes),
            )
            upsert_manifest_entry(container_client, user_id, entry)
            response['manifest_status'] = 'updated'
        except Exception as exc:
            logging.warning('add_new_data: manifest update failed: %s', exc)
            response['manifest_status'] = 'failed'
            response['manifest_error'] = str(exc)
        return response, 200
    except AzureError as exc:
        logging.exception('add_new_data: azure error %s', exc)
        payload = {'status':'error','user_id':user_id,'error':str(exc)}
        if raise_on_error:
            raise
        return payload,500
    except Exception as exc:
        logging.exception('add_new_data: unexpected %s', exc)
        payload={'status':'error','user_id':user_id,'error':str(exc)}
        if raise_on_error:
            raise
        return payload,500
