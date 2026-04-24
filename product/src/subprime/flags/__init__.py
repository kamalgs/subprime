"""Feature flags — GrowthBook-compatible evaluation backed by Postgres.

Public API:

    await init_flags(pool)              # once at startup
    if await is_on("plan_extended"):   # bool flag
        ...
    val = await get_value("advisor_model_basic", "gemini-2.5-flash-lite")
    await set_flag("plan_extended", definition={"defaultValue": True})
    flags = await list_flags()

Flag definitions follow GrowthBook's shape
(https://docs.growthbook.io/lib/python). The simplest case is just
``{"defaultValue": true|false}``. You get targeting rules, % rollouts,
and A/B experiments for free by extending the JSON.

A 30 s in-process TTL cache keeps hot-path evaluations Postgres-free;
``set_flag`` invalidates it so edits go live within the next poll.
"""

from subprime.flags._store import (
    delete_flag,
    get_value,
    init_flags,
    is_on,
    list_flags,
    set_flag,
)
from subprime.flags.context import flag_ctx

__all__ = [
    "delete_flag",
    "flag_ctx",
    "get_value",
    "init_flags",
    "is_on",
    "list_flags",
    "set_flag",
]
