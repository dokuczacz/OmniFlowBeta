"""
Session domain classifier for OmniFlow capability taxonomy.

Maps capability strings to the new 6-category taxonomy:
  PREF  – user preferences and profile settings
  ACT   – actions with external side-effects (mail, tasks, calls)
  PLAN  – planning, scheduling, day-plan construction
  COM   – communication and messaging
  KNOW  – knowledge lookup, history, semantic search
  OPS   – system/operational (status checks, infrastructure ops)

Also declares whether each capability is state-mutating (state_changed=True candidates).
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

# ---------------------------------------------------------------------------
# Domain mapping: capability_prefix -> domain
# Longest-prefix match wins.
# ---------------------------------------------------------------------------
_PREFIX_DOMAIN: Dict[str, str] = {
    # Preferences / profile
    "memory.preferences":           "PREF",

    # Communication (mail + future messaging)
    "mail.send":                    "COM",
    "mail.reply":                   "COM",
    "mail.forward":                 "COM",
    "mail.compose":                 "COM",

    # Actions with external side-effects
    "mail.trash":                   "ACT",
    "mail.delete":                  "ACT",
    "mail.archive":                 "ACT",
    "mail.mark":                    "ACT",
    "task.create":                  "ACT",
    "task.update":                  "ACT",
    "task.complete":                "ACT",
    "task.delete":                  "ACT",

    # Planning
    "planning.":                    "PLAN",
    "task.list":                    "PLAN",
    "task.delayed":                 "PLAN",

    # Knowledge / lookup (read-only mail, history, search)
    "mail.inbox.list":              "KNOW",
    "mail.read":                    "KNOW",
    "mail.summarize":               "KNOW",
    "mail.search":                  "KNOW",
    "memory.interaction.list":      "KNOW",
    "memory.interaction":           "KNOW",

    # OPS – system/infra/status
    "system.":                      "OPS",
    "mail.status":                  "OPS",
    "mail.authorize":               "OPS",

    # Session read-only (OPS)
    "memory.session.summary.get":   "OPS",
    "memory.session.events.list":   "OPS",
}

# Capabilities that mutate persistent state (write / delete / create)
_STATE_MUTATING: FrozenSet[str] = frozenset([
    "mail.send",
    "mail.reply",
    "mail.forward",
    "mail.compose",
    "mail.trash",
    "mail.delete",
    "mail.archive",
    "mail.mark",
    "task.create",
    "task.update",
    "task.complete",
    "task.delete",
    "planning.build_day_plan",
    "memory.preferences.update",
    "memory.interaction.save",
])


def classify_capability(capability: str) -> Tuple[str, bool]:
    """
    Return (domain, is_state_mutating) for a capability string.

    Domain falls back to "OPS" if no prefix matches.
    is_state_mutating is True when the capability writes/deletes persistent data.
    """
    cap = (capability or "").strip()

    # Exact match first
    if cap in _PREFIX_DOMAIN:
        domain = _PREFIX_DOMAIN[cap]
    else:
        # Longest-prefix match
        domain = "OPS"
        best_len = 0
        for prefix, dom in _PREFIX_DOMAIN.items():
            if cap.startswith(prefix) and len(prefix) > best_len:
                domain = dom
                best_len = len(prefix)

    state_mutating = cap in _STATE_MUTATING
    return domain, state_mutating


def domains_for_capabilities(capabilities: list[str]) -> list[str]:
    """Return a deduplicated list of domains for a list of capability strings."""
    seen: list[str] = []
    for cap in capabilities:
        domain, _ = classify_capability(cap)
        if domain not in seen:
            seen.append(domain)
    return seen
