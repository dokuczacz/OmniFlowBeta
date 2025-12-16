# Plan: Reduce OpenAI Run Polling Interval (16.12.2025)

## 1. Locate Polling Logic
- Find where the backend polls OpenAI run status (likely in tool_call_handler or a helper).
- Confirm current polling interval (default is often 1s).

**Effort:** 10–20 min

---

## 2. Refactor Polling Interval
- Change the interval to a lower value (e.g., 0.2s).
- Make the interval configurable via environment variable or config file.

**Effort:** 10–20 min

---

## 3. Test and Monitor
- Test with several tool calls to ensure faster response and no rate limit issues.
- Monitor for excessive API calls or errors.

**Effort:** 20–30 min

---

## 4. Document and Deploy
- Update documentation to reflect the new polling interval and config option.
- Deploy the change to the backend.

**Effort:** 10–20 min

---

### Total Estimated Time: 1–1.5 hours

**Goal:**
Reduce end-to-end latency for tool calls by polling OpenAI run status more frequently.
