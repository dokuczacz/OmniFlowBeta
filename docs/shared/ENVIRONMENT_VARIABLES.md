# Environment variables reference

Copy-paste this catalog when provisioning Azure App Service settings or local `.env.*` templates. Values marked `<secret>` must be filled from your key vault, deployment pipeline, or developer workspace.

## 1. Azure App Service / platform defaults
| Name | Placeholder / default | Notes |
| --- | --- | --- |
| `APPINSIGHTS_INSTRUMENTATIONKEY` | `<secret>` | App Insights instrumentation key (secret). |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | `<secret>` | App Insights connection string (secret). |
| `AZURE_BLOB_CONTAINER_NAME` | `agent-knowledge-base` | Container that hosts user semantic artifacts and caches. |
| `AZURE_HTTP_LOGGING` | `false` | Enable Azure HTTP logging for troubleshooting. |
| `AZURE_PROXY_URL` | `https://your-proxy-host/api/proxy_router` | Optional proxy used by `tool_call_handler`. |
| `AZURE_SDK_LOG_LEVEL` | `info` | Adjust SDK verbosity (`error`, `warning`, `info`, `debug`). |
| `AZURE_STORAGE_CONNECTION_STRING` | `<secret>` | Points to storage account backing Azurite/Prod blobs. |
| `AzureWebJobs.upload_data_or_file.Disabled` | `false` | Feature gate for upload route. |
| `AzureWebJobsStorage` | `<secret>` | Storage account connection used by Functions host. |
| `DEPLOYMENT_STORAGE_CONNECTION_STRING` | `<secret>` | Optional staging storage connection for deployments. |

## 2. Azure Functions runtime and endpoints
| Name | Placeholder / default | Notes |
| --- | --- | --- |
| `FUNCTIONS_WORKER_RUNTIME` | `python` | Runtime used by the Function App. |
| `FUNCTION_URL_BASE` | `http://localhost:7071` | Local URL for tooling; override in Prod (`https://<app>.azurewebsites.net`). |
| `HANDLES_CACHE_TTL_SECONDS` | `600` | Time-to-live for cache-backed context packs. |
| `DEBUG_TOOL_CALL_HANDLER` | `true` / `false` | Enable verbose logs for tool orchestration. |
| `ENABLE_SAVE_INTERACTION` | `true` | Controls whether user interactions persist. |
| `FUNCTION_CODE_PROXY_ROUTER` | `<secret>` | Entry code for `proxy_router`. |
| `FUNCTION_CODE_SAVE_INTERACTION` | `<secret>` | Secures `save_interaction`. |
| `FUNCTION_CODE_ADD_NEW_DATA` | `<secret>` | Secures `add_new_data`. |
| `FUNCTION_CODE_GET_TIME` | `<secret>` | Secures time check endpoint. |
| `FUNCTION_CODE_GET_FILTERED_DATA` | `<secret>` | Secures filtered data fetch. |
| `FUNCTION_CODE_MANAGE_FILES` | `<secret>` | Secures file management endpoints. |
| `FUNCTION_CODE_UPDATE_DATA_ENTRY` | `<secret>` | Secures update action. |
| `FUNCTION_CODE_REMOVE_DATA_ENTRY` | `<secret>` | Secures removal. |
| `FUNCTION_CODE_UPLOAD_DATA_OR_FILE` | `<secret>` | Secures uploads. |
| `FUNCTION_CODE_LIST_BLOBS` | `<secret>` | Secures blob listing. |
| `FUNCTION_CODE_READ_BLOB_FILE` | `<secret>` | Secures single blob read. |
| `FUNCTION_CODE_READ_MANY_BLOBS` | `<secret>` | Secures batch blob read. |
| `FUNCTION_CODE_GET_INTERACTION_HISTORY` | `<secret>` | Secures history retrieval. |

## 3. OpenAI / semantic tooling (WP6 + WP7)
| Name | Placeholder / default | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | `<secret>` | Primary OpenAI or Azure OpenAI key. |
| `OPENAI_ASSISTANT_ID` | `<secret>` | Set when invoking Responses. |
| `OPENAI_PROMPT_ID` | `<secret>` | Default response prompt. |
| `OPENAI_INDEXER_PROMPT_ID` | `<secret>` | Prompt used for WP7 batch indexing. |
| `OPENAI_INDEXER_MODEL` | `gpt-5-mini` | Model that produces semantic artifacts. |
| `OPENAI_CONTEXT_BUILDER_PROMPT_ID` | `pmpt_6952...` | Prompt driving the WP6 context builder. |
| `OPENAI_VECTOR_STORE_ID` | `<optional>` | Required only when using your own vector store. |
| `OPENAI_API_BASE` | `https://api.openai.com` | Override when hitting Azure OpenAI or proxied endpoints. |
| `LLM_RUNTIME` | `assistants` | Determines Responses runtime. |
| `RESPONSES_INCLUDE_TOOLS` | `true` | Allows response loops to call tools. |
| `WP6_DEFAULT_CONTEXT_MODE` | `AUTO` | Auto / FAST / DEEP. |
| `WP6_FAST_MAX_INPUT_TOKENS` | `2000` | FAST routing token cap. |
| `WP6_FAST_MAX_SOURCES` | `4` | FAST source limit. |
| `WP6_FAST_MAX_RAW_BYTES` | `64000` | Raw bytes allowed per FAST pack. |
| `WP6_DEEP_MAX_PACK_TOKENS` | `16000` | Max tokens for DEEP pack. |
| `WP6_DEEP_MAX_CANDIDATE_SOURCES` | `12` | Candidate docs per DEEP run. |
| `WP6_DEEP_MIN_SEMANTIC_SELECTED` | `3` | Minimum to include semantic doc. |
| `WP6_DEEP_MIN_SEMANTIC_CANDIDATES` | `6` | Query candidates for DEEP. |
| `WP6_CONTEXT_PACK_TTL_SECONDS` | `300` | How long cached context persists. |
| `WP6_DEEP_COOLDOWN_SECONDS` | `600` | Cooldown between DEEP paths. |
| `WP7_ENABLED` | `1` | Enable/disable semantic indexer. |
| `WP7_INDEXER_MODE` | `sync` | `sync` or `async`. |
| `WP7_INDEXER_USER_IDS` | `auto` | `auto` or comma-separated IDs. |
| `WP7_TARGET_BATCH_TOKENS` | `1000` | Desired tokens per WP7 batch. |
| `WP7_HARD_MIN_BATCH_TOKENS` | `600` | Minimum enforced tokens. |
| `WP7_MAX_WAIT_SECONDS` | `300` | Wait time for batching. |
| `WP7_MAX_ITEMS_PER_RUN` | `25` | Items allowed per WP7 run. |
| `WP7_MAX_OUTPUT_TOKENS_PER_ITEM` | `180` | Response token limit. |
| `WP7_ALLOWED_CATEGORIES` | `PE,UI,ML,LO,PS,TM,SYS,GEN,ID` | Allowed semantic categories. |
| `WP7_UNCATEGORIZED_CONFIDENCE_LT` | `0.6` | Threshold for `uncategorized` bucket. |

## 4. Gmail OAuth helpers
| Name | Placeholder / default | Notes |
| --- | --- | --- |
| `GMAIL_OAUTH_CLIENT_ID` | `<secret>` | Gmail OAuth client ID. |
| `GMAIL_OAUTH_CLIENT_SECRET` | `<secret>` | Gmail OAuth client secret. |
| `GMAIL_OAUTH_REDIRECT_URI` | `http://localhost:7071/api/custom_bridge` | Redirect URI for OAuth handshake (handled via GET on `custom_bridge`). |
| `GMAIL_OAUTH_SCOPES` | `https://mail.google.com/` | Gmail scopes requested. |
| `GMAIL_OAUTH_PROMPT` | `consent` | Prompt presented to Gmail user. |

## 5. Frontend / UI helpers
| Name | Placeholder / default | Notes |
| --- | --- | --- |
| `BACKEND_BASE_URL` | `http://localhost:7071` | Used by Streamlit/legacy tooling. |
| `DEFAULT_USER_ID` | `guest` | Optional default user ID for local dev. |
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:7071` | Next.js UI → backend base URL. |
| `AUTH_SECRET` | `<secret>` | Used by the Next.js AI chatbot webhook. |
| `AI_GATEWAY_API_KEY` | `<secret>` | Vercel AI Gateway API key (if not using OIDC). |
| `BLOB_READ_WRITE_TOKEN` | `<secret>` | Vercel Blob Store token referenced by the chatbot. |
| `POSTGRES_URL` | `<secret>` | Optional Vercel Postgres database. |
| `REDIS_URL` | `<secret>` | Optional Redis cache/queue store. |

## Versioning notes
- Keep this list aligned with `backend/local.settings.template.json` and `.env.example`.
- Secrets (marked `<secret>`) must never be committed. Use Azure Key Vault, GitHub secrets, or environment-specific pipelines.
