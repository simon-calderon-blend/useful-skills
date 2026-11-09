"""Refuse anything that is not a dev/test account before a single AWS call is made."""

from __future__ import annotations

from typing import Any

from padding_gate.resources import ENV_ACCOUNTS

SENSITIVE_MARKERS = ("PROD", "MASTER", "SECURITY", "SENSITIVE")
SENSITIVE_PROFILES = frozenset({"civileza-prod", "civileza-mpa"})


class GuardError(Exception):
    """The requested profile or account is not one this tool may touch."""


def check_profile(profile: str) -> None:
    if not profile:
        raise GuardError("--profile is required; this tool never falls back to the default profile")
    upper = profile.upper()
    if profile in SENSITIVE_PROFILES or any(m in upper for m in SENSITIVE_MARKERS):
        raise GuardError(f"refusing sensitive profile {profile!r}: this tool is dev/test only")


def verify_account(sts: Any, env: str) -> str:
    """The caller's account, if and only if it is the account of ``env``."""
    account = sts.get_caller_identity()["Account"]
    expected = ENV_ACCOUNTS[env]
    if account != expected:
        raise GuardError(
            f"profile resolves to account {account}, but env {env!r} is account {expected}"
        )
    return account
