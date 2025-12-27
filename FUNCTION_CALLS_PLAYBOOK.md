# OmniFlow — Function Calls Playbook (strict, copy‑paste)

Cel: dać agentowi **jedno źródło prawdy** jak poprawnie wywoływać funkcje (Actions), z limitami i bez “błądzenia”.

Zasady ogólne (must)
- Zawsze podawaj `user_id` (albo `x-user-id` header). Jeśli brak → backend użyje `default` (to może mieszać sesje).
- Preferuj operacje **batch**:
  - `read_many_blobs` zamiast wielu `read_blob_file`
  - `get_filtered_data` zamiast “czytam cały plik i filtruję w modelu”
- Nie pobieraj pełnych plików, jeśli wystarczy ogon (`tail_lines`) albo metadane (`list_blobs`).
- Utrzymuj limity kontekstu: pobieraj tylko minimalne dane potrzebne do odpowiedzi.

Uwaga o `code`
- Każdy endpoint ma wymagany `code` (function key) w query. W repo jest to utrzymywane w `backend/custom_gpt_tools/actions_openapi.json` oraz w env (Azure).
- W przykładach poniżej używam placeholderów typu `<CODE_...>` — uzupełnij zgodnie z deploymentem.

---

## 1) list_blobs (GET)

Cel: lista plików w namespace użytkownika.

**Przykład**
`GET /api/list_blobs?prefix=&user_id=default&code=<CODE_LIST_BLOBS>`

Opcja: `include_meta=1` (zwraca też `blobs_meta` z `size`/`last_modified`).

---

## 2) read_blob_file (GET)

Cel: odczyt pojedynczego pliku (n=1).

**Przykład**
`GET /api/read_blob_file?file_name=TM.json&user_id=default&code=<CODE_READ_BLOB_FILE>`

---

## 3) read_many_blobs (POST) — NOWE (preferowane do przeglądu)

Cel: odczyt wielu plików w jednym wywołaniu, z limitami i opcjonalnym “tail”.

**Przykład: n plików**
`POST /api/read_many_blobs?code=<CODE_READ_MANY_BLOBS>`
```json
{
  "user_id": "default",
  "files": ["TM.json", "LO.json", "PS.json"],
  "max_bytes_per_file": 262144,
  "parse_json": true
}
```

**Przykład: ogon (JSONL / tekst)**
`POST /api/read_many_blobs?code=<CODE_READ_MANY_BLOBS>`
```json
{
  "user_id": "default",
  "files": ["interactions/semantic/index.jsonl", "interactions/indexer_queue.jsonl"],
  "tail_lines": 50,
  "tail_bytes": 65536,
  "parse_json": false
}
```

---

## 4) get_filtered_data (POST)

Cel: filtr serwerowy po kluczu/wartości (bez czytania całego pliku).

`POST /api/get_filtered_data?code=<CODE_GET_FILTERED_DATA>`
```json
{
  "user_id": "default",
  "target_blob_name": "TM.json",
  "filter_key": "status",
  "filter_value": "todo"
}
```

---

## 5) add_new_data (POST)

Cel: dodać wpis do pliku JSON (entry jako string JSON).

`POST /api/add_new_data?code=<CODE_ADD_NEW_DATA>`
```json
{
  "user_id": "default",
  "target_blob_name": "TM.json",
  "new_entry": "{\"id\":\"TM.001.202512271230\",\"timestamp\":\"2025-12-27T12:30:00Z\",\"content\":\"Test\"}"
}
```

---

## 6) update_data_entry (POST)

Cel: znaleźć pierwszy rekord po (find_key/find_value) i zaktualizować pole.

`POST /api/update_data_entry?code=<CODE_UPDATE_DATA_ENTRY>`
```json
{
  "user_id": "default",
  "target_blob_name": "TM.json",
  "find_key": "id",
  "find_value": "TM.001.202512271230",
  "update_key": "status",
  "update_value": "in-progress"
}
```

---

## 7) remove_data_entry (POST)

Cel: usunąć wpisy pasujące do key/value.

`POST /api/remove_data_entry?code=<CODE_REMOVE_DATA_ENTRY>`
```json
{
  "user_id": "default",
  "target_blob_name": "TM.json",
  "key_to_find": "id",
  "value_to_find": "TM.001.202512271230"
}
```

---

## 8) upload_data_or_file (POST)

Cel: nadpisać cały plik (tekst/JSON).

`POST /api/upload_data_or_file?code=<CODE_UPLOAD_DATA_OR_FILE>`
```json
{
  "user_id": "default",
  "target_blob_name": "GEN.json",
  "file_content": "[]"
}
```

---

## 9) manage_files (POST)

Cel: delete/rename (legacy).

`POST /api/manage_files?code=<CODE_MANAGE_FILES>`
```json
{ "user_id": "default", "operation": "list", "prefix": "" }
```

---

## 10) save_interaction / get_interaction_history

Cel: logi interakcji (raw). Preferuj semantykę WP7 do budowy kontekstu (WP6).

`POST /api/save_interaction?code=<CODE_SAVE_INTERACTION>`
```json
{
  "user_id": "default",
  "user_message": "Hi",
  "assistant_response": "Hello",
  "thread_id": "handle_xxx",
  "tool_calls": [],
  "metadata": {}
}
```

`GET /api/get_interaction_history?user_id=default&limit=50&offset=0&code=<CODE_GET_INTERACTION_HISTORY>`

