# OmniFlow – plan optymalizacji latency (pakiety od najłatwiejszych do najtrudniejszych)

## Schemat logiczny: gdzie ucieka czas

1) **Handler → OpenAI orchestration**
- zbędne `runs.list`, nadmiar `runs.retrieve`, statyczne `sleep/backoff`, `messages.list` na końcu

2) **Tool execution path → stały narzut ~2s / tool**
- `proxy_router` jako HTTP-hop (call-through) dodaje ~2s na *każde* narzędzie, mimo że same funkcje robią ms

3) **RAG/vector store nie działa (fałszywe testy)**
- log typu: „client does not support `tool_resources`… falling back” oznacza, że vector store nie jest podpinany do runa


---


## Pakiet 0 — „Wytnij zbędne hamulce w handlerze”  
**Status:** ✅ Zrealizowane (grudzień 2025, potwierdzone w kodzie i historii czatu)
**Trudność:** łatwe  
**Priorytet:** najwyższy

### Wyniki
- Zredukowano liczbę requestów do OpenAI, usunięto sztuczne pauzy.
- `wait_for_open_runs()` tylko w trybie debug.
- Brak statycznych sleep/backoff w polling loop.
- `submit_tool_outputs` natychmiast po tool call.
- `messages.list` tylko raz na końcu.
   - Potwierdzono: liczba GET /runs spadła, zniknęły puste przerwy, wall-time skrócony o 5–7s na request.
   - Zmiany potwierdzone w kodzie i testach (grudzień 2025).

---


---

## Pakiet 1 — „Napraw RAG: `tool_resources` musi działać”
**Status:** ⏳ W trakcie (logi pokazują fallback, vector store nie podpięty)
**Trudność:** łatwe–średnie  
**Priorytet:** wysoki

### Cel
   - Upewnić się, że vector store (`tool_resources`) jest poprawnie podpinany do runa.
   - Sprawdzić i naprawić konfigurację, aby nie było komunikatu „client does not support `tool_resources`… falling back”.

---

## Pakiet 2 — „Zoptymalizuj ścieżkę tool execution”
**Status:** ⏳ Do zrobienia
**Trudność:** średnie  
**Priorytet:** średni

### Cel
   - Zredukować narzut ~2s na każde wywołanie narzędzia przez proxy_router.
   - Rozważyć batchowanie, bezpośrednie wywołania funkcji lub optymalizację proxy.
Prawdziwe testy pamięci/wektorów (obecnie są fałszywe, jeśli jest fallback).

### Kroki
1) Zidentyfikuj warstwę klienta/SDK, która wysyła `runs.create`.
2) Zaktualizuj klienta/SDK lub przejdź na wywołanie REST tak, aby `tool_resources` weszło do payloadu.
3) Dodaj log “vector store attached OK” + test E2E: query, które musi zaciągnąć wynik z `file_search`.

### DoD
- znika log „does not support tool_resources…”
- RAG działa powtarzalnie


---


## Pakiet 2 — „Zabij stały narzut ~2s na każde narzędzie”  
**Status:** ✅ Zrealizowane (grudzień 2025)
**Trudność:** średnie  
**Priorytet:** bardzo wysoki

### Wyniki
- Wszystkie główne narzędzia (add_new_data, get_current_time, get_filtered_data, list_blobs, read_blob_file, remove_data_entry, update_data_entry, upload_data_or_file, manage_files) są teraz wywoływane in-process (bez HTTP proxy_router).
- Czas tool call spadł z ~4s do ~100ms.
- proxy_router nadal dostępny dla zewnętrznych/legacy, ale handler używa callables.
- Potwierdzono: narzut HTTP wyeliminowany, backend znacznie szybszy.

---
## Podsumowanie stanu (grudzień 2025)

- Backend zoptymalizowany: Pakiet 0 i 2 wdrożone, narzut handlera i tooli zminimalizowany.
- Główne bottleneck: czas oczekiwania na OpenAI run (zewnętrzne API).
- RAG/tool_resources: SDK nie wspiera, otwarty punkt do dalszych prac.

---

## Next Steps & Priorities (2026)

1. **Pakiet 1 — RAG/tool_resources**  
   - Priorytet: wysoki (gdy SDK/REST pozwoli)  
   - Działania: testować nowe SDK, przejść na REST jeśli trzeba, potwierdzić E2E.
2. **Pakiet 3 — Streaming (SSE)**  
   - Priorytet: średni-wysoki  
   - Działania: dodać tryb stream, zredukować polling, poprawić UX.
3. **Pakiet 4 — Dynamic tool registry**  
   - Priorytet: średni  
   - Działania: zawężanie tools per turn, mniejsze payloady, szybszy wybór.
4. **Pakiet 5 — Responses API**  
   - Priorytet: strategiczny  
   - Działania: migracja do Responses API, A/B testy latency i kosztów.
5. **Frontend/UI**  
   - Priorytet: średni  
   - Działania: dalsze optymalizacje feedbacku i perceived latency.

**Szacowany nakład pracy na dokumentację i planowanie: 1.5–2h.**


---

## Pakiet 3 — „Streaming zamiast pollingu (SSE)”
**Trudność:** średnie–trudne  
**Priorytet:** średni–wysoki (duży zysk UX, zmniejsza polling)

### Cel
Zredukować polling + dać natychmiastowy feedback w UI.

### Kroki
1) Dodaj feature flag `STREAM_RUNS=true`.
2) W trybie stream:
   - konsumuj eventy runa
   - gdy `requires_action` → wykonaj tools → `submit_tool_outputs`
   - kontynuuj stream do `completed`
3) UI: pokazuj “in progress” od pierwszego eventu (czas do pierwszego sygnału).

### DoD
- `GET /runs/{id}` ≈ 0 (lub minimalne)
- “time-to-first-signal” w UI spada poniżej ~1s


---

## Pakiet 4 — „Dynamic tool registry (zawężanie tools per turn)”
**Trudność:** średnie  
**Priorytet:** średni (redukcja payloadu i ‘tool confusion’)

### Cel
Mniej narzędzi = mniejszy request + szybsze wybory narzędzi.

### Kroki
1) Zdefiniuj paczki narzędzi (np. Core/BlobRead/BlobWrite/Memory/KB/Admin).
2) Prosta detekcja intencji (reguły lub mini-klasyfikator) wybiera paczkę.
3) Fallback: jeśli model “nie da rady”, uruchom drugi run z szerszą paczką.

### DoD
- mniej przypadkowych tool calls
- spadek tokenów/payloadu i krótszy średni run


---

## Pakiet 5 — „Migracja z Assistants do Responses API”
**Trudność:** trudne  
**Priorytet:** strategiczny (docelowy runtime)

### Cel
Mniej narzutu orkiestracji i łatwiejszy streaming-first.

### Bezpieczna ścieżka (adapter)
1) Zrób adapter `LLMClient` z metodami:
   - `add_user_message(thread_or_state, text)`
   - `run_turn(tools, context)`
   - `handle_tool_calls(...)`
2) Implementacja A = obecny Assistants.
3) Implementacja B = Responses API.
4) Przełącznik ENV: `LLM_RUNTIME=assistants|responses`.

### DoD
- UI i tool layer są niezależne od runtime
- możliwość A/B testów latency i kosztów


---

## Pakiet równoległy — bugfix `add_new_data` 500
**Trudność:** łatwe  
**Priorytet:** wysoki (stabilność)

### Objaw
`Expecting value: line 1 column 1` (zwykle: JSON parse pustego stringa / nie-JSON).

### DoD
- narzędzie nie zwraca 500 dla plików `.md` / pustych treści
- model nie “kręci się” w pętli naprawczej


---

## Minimalna kolejność wdrożenia (ROI)
1) **Pakiet 0** (usuń sleeps/backoff + zbędne list/retrieve + submit od razu)  
2) **Pakiet 2** (in-process tool dispatch – największa dźwignia)  
3) **Pakiet 1** (RAG tool_resources – żeby testy były prawdziwe)  
4) **Pakiet 3** (streaming)  
5) **Pakiet 4** (dynamic tools)  
6) **Pakiet 5** (Responses adapter + migracja)
