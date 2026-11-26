from __future__ import annotations

from copy import deepcopy
from typing import Any

LEGACY_ALIASES = {
    "worker-l3": "worker-l2",
    "worker-vision-deep": "worker-vision",
}


def migrate_legacy_routing(routing: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(routing)
    models = migrated.get("models")
    if isinstance(models, dict):
        for legacy, replacement in LEGACY_ALIASES.items():
            if legacy not in models:
                continue
            models.setdefault(replacement, models[legacy])
            del models[legacy]
    for table_name in ("routes", "autoRoutes"):
        table = migrated.get(table_name)
        if not isinstance(table, dict):
            continue
        if "L3" in table:
            table.setdefault("L2", table["L3"])
            del table["L3"]
        for routes in table.values():
            if not isinstance(routes, dict):
                continue
            for modality, alias in list(routes.items()):
                if alias in LEGACY_ALIASES:
                    routes[modality] = LEGACY_ALIASES[alias]
    return migrated
