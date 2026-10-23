"""Role -> model table for the cascade-control probe.

Models come from a committed JSON config, not from code; the config hash goes
into every trace so a run can be tied to the exact table it used.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_ROLES_PATH = Path(__file__).parent / "roles.json"


@dataclass(frozen=True)
class RoleConfig:
    default: str
    roles: dict[str, str]
    price_per_mtok: dict[str, float]
    sha256: str

    def model_for(self, role: str) -> str:
        return self.roles.get(role, self.default)


@lru_cache(maxsize=4)
def load_roles(path: str | Path = DEFAULT_ROLES_PATH) -> RoleConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return RoleConfig(
        default=raw["default"],
        roles=dict(raw.get("roles", {})),
        price_per_mtok=dict(raw["price_per_mtok"]),
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
    )
