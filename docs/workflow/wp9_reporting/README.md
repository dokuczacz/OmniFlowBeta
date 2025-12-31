# WP9 — Raportowanie (lokalne JSONL)

Ten folder zawiera lokalne artefakty raportowania (JSONL) utrzymywane deterministycznie przez dedykowany skrypt, bez dowolności formatowania przez agenta.

**Cel:** szybkie i trwałe logowanie przebiegu pracy dla agentów AI (`plan`/`execution`/`best_practice`) w formacie JSONL.

**Ważne:** raporty są lokalne (Azurite jest nietrwałe) — zapis jest do plików w tym folderze.

## Pliki
- `schema_v1.py` — strict schema wpisu (Pydantic).
- `append_report_entry.py` — jedyna dozwolona ścieżka dopisywania wpisów (enforces schema + generuje `entry_id` i `timestamp_utc`).
- `local_jsonl_store.py` — append JSONL z lockfile (`.lock`) dla minimalnej ochrony przed równoległymi zapisami.
- `reports.jsonl` — docelowy plik (tworzy się automatycznie przy pierwszym wpisie).
- `templates/*.json` — wzory inputów do skryptu (to nie są pliki JSONL).

## Konwencja wpisów (docelowo 1× plan + 1× execution + 1× best_practice)
- `plan`: jeden wpis opisujący co i dlaczego wdrażamy.
- `execution`: jeden wpis potwierdzający wykonanie (status + ewentualnie runtime/timings/commit).
- `best_practice`: jeden wpis zawierający listę wszystkich best practices z sesji (`best_practice.items[]`), powiązany z execution przez `best_practice.source_entry_id`.

## Template inputy
- `templates/wp9.plan.input.json`
- `templates/wp9.execution.input.json`
- `templates/wp9.best_practice.input.json`
  - `best_practice.source_entry_id` zostaje jako placeholder `TO_BE_SET_AFTER_EXECUTION` i powinien zostać podstawiony na realny `entry_id` wpisu `execution`.

## Użycie (dry-run)
```bash
python docs/workflow/wp9_reporting/append_report_entry.py --input docs/workflow/wp9_reporting/templates/wp9.execution.input.json --dry-run
```

## Użycie (append do lokalnego reports.jsonl)
```bash
python docs/workflow/wp9_reporting/append_report_entry.py --input docs/workflow/wp9_reporting/templates/wp9.plan.input.json
python docs/workflow/wp9_reporting/append_report_entry.py --input docs/workflow/wp9_reporting/templates/wp9.execution.input.json
python docs/workflow/wp9_reporting/append_report_entry.py --input docs/workflow/wp9_reporting/templates/wp9.best_practice.input.json
```

## Notatki techniczne (Windows)
- Skrypt czyta input JSON jako `utf-8-sig` (obsługa BOM).
