import pytest

from padding_gate.guards import GuardError, check_profile, verify_account
from padding_gate.resources import resources_for


@pytest.mark.parametrize(
    "profile",
    [
        "ADR-PROD-MEDICALAUDIT-RO",
        "ADR-PROD-LOGS",
        "ADRES-MASTER",
        "ADR-SECURITY",
        "ADR-PROD-MEDICALAUDIT-SENSITIVE",
        "adr-prod-lowercase",
        "civileza-prod",
        "civileza-mpa",
        "",
    ],
)
def test_sensitive_or_empty_profiles_are_refused(profile):
    with pytest.raises(GuardError):
        check_profile(profile)


@pytest.mark.parametrize("profile", ["ADR-DEV-MEDICALAUDIT", "ADR-TEST-MEDICALAUDIT"])
def test_dev_and_test_profiles_pass(profile):
    check_profile(profile)


def test_account_matching_env_is_returned(stubbed):
    sts, stub = stubbed("sts")
    stub.add_response(
        "get_caller_identity",
        {"Account": "276553701208", "Arn": "arn:aws:sts::276553701208:assumed-role/x/y", "UserId": "u"},
    )
    assert verify_account(sts, "test") == "276553701208"


def test_profile_pointing_at_another_account_is_refused(stubbed):
    sts, stub = stubbed("sts")
    stub.add_response(
        "get_caller_identity",
        {"Account": "072055531089", "Arn": "arn:aws:sts::072055531089:assumed-role/x/y", "UserId": "u"},
    )
    with pytest.raises(GuardError, match="072055531089"):
        verify_account(sts, "test")


def test_resource_names_derive_from_env():
    res = resources_for("dev")
    assert res.table == "adr-dev-medicalaudit-doc-extraction-chunks"
    assert res.bucket == "adr-dev-medicalaudit-workarea"
    assert res.queue_name == "adr-dev-medicalaudit-doc-extraction-chunks-conveyor"
    assert res.appconfig_app == "adr-dev-medicalaudit-doc-extraction-appconfig"
    assert res.account == "072055531089"


def test_prod_is_not_an_env():
    with pytest.raises(ValueError):
        resources_for("prod")
