import json

import pytest

from padding_gate.appconfig import AppConfigError, load_live_config

APP = "adr-dev-medicalaudit-doc-extraction-appconfig"
PROFILES = {"batch": "pb", "storage": "ps", "extraction": "pe", "ADM": "pa"}
STORAGE = {
    "work": {
        "run_configs": "_global/run-configs/",
        "run_config_pointers": "staging/document-extraction/run-config/",
    }
}
EXTRACTION = {"extractable_doc_codes": ["ADM", "PDX", "IPO"], "always_ondemand_doc_codes": ["FAC"]}


def _deployment(number, name, version, state="COMPLETE"):
    return {
        "DeploymentNumber": number,
        "ConfigurationName": name,
        "ConfigurationVersion": str(version),
        "State": state,
    }


def _stub_discovery(stub, apps, deployments):
    stub.add_response("list_applications", {"Items": apps}, {})
    stub.add_response(
        "list_environments",
        {"Items": [{"ApplicationId": "app1", "Id": "env1", "Name": "dev"}]},
        {"ApplicationId": "app1"},
    )
    stub.add_response(
        "list_configuration_profiles",
        {"Items": [{"ApplicationId": "app1", "Id": pid, "Name": n} for n, pid in PROFILES.items()]},
        {"ApplicationId": "app1"},
    )
    stub.add_response(
        "list_deployments",
        {"Items": deployments},
        {"ApplicationId": "app1", "EnvironmentId": "env1"},
    )


def _stub_content(stub, profile_id, version, payload):
    stub.add_response(
        "get_hosted_configuration_version",
        {"Content": json.dumps(payload).encode(), "ContentType": "application/json"},
        {"ApplicationId": "app1", "ConfigurationProfileId": profile_id, "VersionNumber": version},
    )


def test_reads_the_last_complete_deployment_not_the_newest_version(stubbed):
    appconfig, stub = stubbed("appconfig")
    _stub_discovery(
        stub,
        apps=[
            {"Id": "e1copy", "Name": "e1-" + APP},
            {"Id": "app1", "Name": APP},
        ],
        deployments=[
            # Newest first, as the API returns them; batch v4 never finished.
            _deployment(9, "batch", 4, state="ROLLED_BACK"),
            _deployment(8, "extraction", 2),
            _deployment(7, "storage", 5),
            _deployment(6, "batch", 3),
        ],
    )
    _stub_content(stub, "pb", 3, {"min_records_per_job": 100})
    _stub_content(stub, "ps", 5, STORAGE)
    _stub_content(stub, "pe", 2, EXTRACTION)

    live = load_live_config(appconfig, APP, "dev")

    assert live.min_records == 100
    assert live.run_configs_prefix == "_global/run-configs/"
    assert live.pointers_prefix == "staging/document-extraction/run-config/"
    assert live.batch_doc_codes == frozenset({"ADM", "PDX", "IPO"})
    assert live.sources["batch"] == "deployment #6 (version 3)"


def test_ondemand_codes_are_not_batch_codes(stubbed):
    appconfig, stub = stubbed("appconfig")
    _stub_discovery(
        stub,
        apps=[{"Id": "app1", "Name": APP}],
        deployments=[_deployment(3, "extraction", 1), _deployment(2, "storage", 1), _deployment(1, "batch", 1)],
    )
    _stub_content(stub, "pb", 1, {"min_records_per_job": 100})
    _stub_content(stub, "ps", 1, STORAGE)
    _stub_content(
        stub, "pe", 1, {"extractable_doc_codes": ["ADM", "FAC"], "always_ondemand_doc_codes": ["FAC"]}
    )

    live = load_live_config(appconfig, APP, "dev")

    assert live.batch_doc_codes == frozenset({"ADM"})


def test_only_a_lookalike_application_is_an_error(stubbed):
    appconfig, stub = stubbed("appconfig")
    stub.add_response("list_applications", {"Items": [{"Id": "e1copy", "Name": "e1-" + APP}]}, {})

    with pytest.raises(AppConfigError, match="no AppConfig application named"):
        load_live_config(appconfig, APP, "dev")


def test_profile_without_a_complete_deployment_is_an_error(stubbed):
    appconfig, stub = stubbed("appconfig")
    _stub_discovery(
        stub,
        apps=[{"Id": "app1", "Name": APP}],
        deployments=[_deployment(2, "storage", 1), _deployment(1, "batch", 1, state="DEPLOYING")],
    )

    with pytest.raises(AppConfigError, match="'batch'"):
        load_live_config(appconfig, APP, "dev")


def test_legacy_flat_storage_keys_still_resolve(stubbed):
    appconfig, stub = stubbed("appconfig")
    _stub_discovery(
        stub,
        apps=[{"Id": "app1", "Name": APP}],
        deployments=[_deployment(3, "extraction", 1), _deployment(2, "storage", 1), _deployment(1, "batch", 1)],
    )
    _stub_content(stub, "pb", 1, {"min_records_per_job": 50})
    _stub_content(stub, "ps", 1, {"run_configs": "rc/", "run_config_pointers": "ptr/"})
    _stub_content(stub, "pe", 1, EXTRACTION)

    live = load_live_config(appconfig, APP, "dev")

    assert (live.min_records, live.run_configs_prefix, live.pointers_prefix) == (50, "rc/", "ptr/")


def test_corrupt_profile_content_is_an_appconfig_error(stubbed):
    appconfig, stub = stubbed("appconfig")
    _stub_discovery(
        stub,
        apps=[{"Id": "app1", "Name": APP}],
        deployments=[_deployment(3, "extraction", 1), _deployment(2, "storage", 1), _deployment(1, "batch", 1)],
    )
    stub.add_response("get_hosted_configuration_version", {"Content": b"{not json"}, None)

    with pytest.raises(AppConfigError, match="batch"):
        load_live_config(appconfig, APP, "dev")


def test_missing_min_records_is_an_appconfig_error(stubbed):
    appconfig, stub = stubbed("appconfig")
    _stub_discovery(
        stub,
        apps=[{"Id": "app1", "Name": APP}],
        deployments=[_deployment(3, "extraction", 1), _deployment(2, "storage", 1), _deployment(1, "batch", 1)],
    )
    _stub_content(stub, "pb", 1, {"max_records_per_job": 10})
    _stub_content(stub, "ps", 1, STORAGE)
    _stub_content(stub, "pe", 1, EXTRACTION)

    with pytest.raises(AppConfigError, match="min_records_per_job"):
        load_live_config(appconfig, APP, "dev")


def test_duplicate_application_names_say_so(stubbed):
    appconfig, stub = stubbed("appconfig")
    stub.add_response("list_applications", {"Items": [{"Id": "a", "Name": APP}, {"Id": "b", "Name": APP}]}, {})
    with pytest.raises(AppConfigError, match="found 2"):
        load_live_config(appconfig, APP, "dev")
