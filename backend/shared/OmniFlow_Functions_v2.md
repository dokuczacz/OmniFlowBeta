
# OmniFlow_Functions_v2.md
Pełna specyfikacja funkcji systemowych dostępnych dla agenta.

---

## 🔵 GET — operacje odczytu (najwyższy priorytet)

### ▶ list_blobs
Zwraca listę plików.

Przykład:
```
{
 "action": "list_blobs",
 "params": { "operation": "list" }
}
```

### ▶ read_blob_file
Zwraca zawartość wskazanego pliku (JSON, TXT, MD).

```
{
 "action": "read_blob_file",
 "params": { "file_name": "TM.json" }
}
```

### ▶ get_current_time
```
{
 "action": "get_current_time",
 "params": {}
}
```

### ▶ get_filtered_data
Filtrowanie JSON wg klucza/wartości.

```
{
 "action": "get_filtered_data",
 "params": {
   "file_name": "tasks.json",
   "key_to_find": "status",
   "value_to_find": "todo"
 }
}
```

---

## 🟢 CRUD — operacje na danych JSON

### ▶ add_new_data
Dodanie wpisu RAW JSON do pliku.

```
{
 "action": "add_new_data",
 "params": {
   "target_blob_name": "PS.json",
   "new_entry": "{...JSON...}"
 }
}
```

### ▶ update_data_entry
Aktualizacja istniejącego wpisu.

```
{
 "action": "update_data_entry",
 "params": {
   "target_blob_name": "TM.json",
   "find_key": "id",
   "find_value": "TM.001",
   "update_key": "status",
   "update_value": "done"
 }
}
```

### ▶ remove_data_entry
Usunięcie wpisu.

```
{
 "action": "remove_data_entry",
 "params": {
   "target_blob_name": "GEN.json",
   "key_to_find": "id",
   "value_to_find": "GEN.002"
 }
}
```

---

## 🟣 SYSTEM — operacje plikowe i techniczne

### ▶ manage_files (legacy)
Może służyć do rename/delete.  
⚠ **Nie używać do listowania.**

```
{
 "action": "manage_files",
 "params": {
   "operation": "delete",
   "file_name": "old.json"
 }
}
```

### ▶ upload_data_or_file
Nadpisanie pliku treścią RAW.

```
{
 "action": "upload_data_or_file",
 "params": {
   "target_blob_name": "SYS.json",
   "file_content": "{...}"
 }
}
```

---

## 🟡 BOOT SEQUENCE — obowiązkowy start agenta
1. get_current_time  
2. list_blobs  
3. read_blob_file (TM, PS, PE, GEN, SYS)

Agent musi załadować te pliki przed rozpoczęciem logiki sesji.

---
