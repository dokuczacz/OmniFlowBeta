# save_interaction
Persist user-assistant interactions inside users/{user_id}/interactions/.

Endpoints:
- POST /api/save_interaction

Payload:
- user_message (required)
- ssistant_response (required)
- 	hread_id (optional)
- 	ool_calls (optional)
- metadata (optional)

Notes:
- Each interaction is saved as interactions/{interaction_id}.json and indexed via interactions/index.jsonl.
- get_interaction_history is deprecated; new consumers should read the index/binaries directly.
- Requires X-User-Id and the save interaction function key.
