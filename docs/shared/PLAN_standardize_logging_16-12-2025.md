# Logging Standardization Plan for 16.12.2025

## Goal
Ensure all assistant-related functions log the following minimum data for every interaction:

- User's message
- Assistant's response
- Thread ID (for conversation tracking)
- All tool calls made:
  - Tool name
  - Arguments passed
  - Result returned
  - Success/failure status
- Metadata (assistant_id, source)
- Timestamp (ISO 8601 format)

## Steps

1. **Audit All Functions**
   - Identify all functions that handle user-assistant interactions (tool_call_handler, save_interaction, etc.).
   - Review their current logging payloads.
   - Effort: 20 min

2. **Refactor Logging Logic**
   - Update each function to ensure the above fields are always included in the log entry.
   - Add missing fields (e.g., timestamp, metadata) where necessary.
   - Effort: 40 min

3. **Centralize Logging Utility (if not already present)**
   - Create or update a shared logging utility to enforce the schema.
   - Effort: 30 min

4. **Test Logging Consistency**
   - Trigger interactions through all relevant endpoints.
   - Verify logs in blob storage for completeness and correct schema.
   - Effort: 30 min

5. **Document Logging Schema**
   - Update DATA_EXTRACTION_IMPLEMENTATION.md and relevant docs to reflect the enforced schema.
   - Effort: 15 min

## Total Estimated Time: 2–2.5 hours

## Deliverable
- All interaction logs (across all functions) will contain the required fields for every entry, ensuring consistency for analysis, debugging, and compliance.
