---
name: omniflow-azure-blob-ops
description: Azure Blob and Azurite operator commands for existence checks, counts, and sampling with env-var-only secrets.
---

# omniflow-azure-blob-ops

## When to apply
Use for Blob/Azurite checks:
- blob existence,
- prefix counts,
- latest blob sampling,
- azurite vs azure quick comparisons.

## Composition
- Append mode.
- Provide concise command blocks.

## Output (MUST)
- Copy/paste commands.
- One-line success signal.

## Rules
- Never inline connection strings or tokens.
- Use env vars such as `AZURE_STORAGE_CONNECTION_STRING`.
- Prefer targeted checks over full scans.

## Example templates
```powershell
python -c "import os; from azure.storage.blob import BlobServiceClient; c=BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING']).get_container_client('<container>'); print(c.get_blob_client('<blob>').exists())"

python -c "import os; from azure.storage.blob import BlobServiceClient; c=BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING']).get_container_client('<container>'); print(sum(1 for b in c.list_blobs(name_starts_with='<prefix>') if b.name.endswith('.json')))"
```
