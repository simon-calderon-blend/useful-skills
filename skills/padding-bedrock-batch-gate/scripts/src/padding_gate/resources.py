"""Names of everything the tool touches, derived from the environment alone.

There is deliberately no override flag for the table, bucket or queue: a name the
operator can type is a name that can point at prod. prod is not in ENV_ACCOUNTS,
so it cannot be reached at all.
"""

from __future__ import annotations

from dataclasses import dataclass

ENV_ACCOUNTS = {"dev": "072055531089", "test": "276553701208"}
REGION = "us-east-1"
# WORKAREA_BASE_PREFIX of the doc-extraction stacks.
BASE_PREFIX = "audit-processes"


@dataclass(frozen=True)
class Resources:
    env: str

    @property
    def _prefix(self) -> str:
        return f"adr-{self.env}-medicalaudit-"

    @property
    def account(self) -> str:
        return ENV_ACCOUNTS[self.env]

    @property
    def table(self) -> str:
        return f"{self._prefix}doc-extraction-chunks"

    @property
    def bucket(self) -> str:
        return f"{self._prefix}workarea"

    @property
    def queue_name(self) -> str:
        return f"{self._prefix}doc-extraction-chunks-conveyor"

    @property
    def appconfig_app(self) -> str:
        # Matched by EXACT name: dev also carries e1-adr-dev-...-appconfig copies.
        return f"{self._prefix}doc-extraction-appconfig"


def resources_for(env: str) -> Resources:
    if env not in ENV_ACCOUNTS:
        raise ValueError(f"unknown env {env!r}; only {sorted(ENV_ACCOUNTS)} are supported")
    return Resources(env)
