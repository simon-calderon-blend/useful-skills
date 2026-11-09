import pytest

from iae_launch import envs


def test_only_dev_and_test_exist():
    assert set(envs.ENVS) == {"dev", "test"}


def test_test_profile_is_not_the_stale_runner_one():
    assert envs.get_env("test").profile == "ADR-TEST-MEDICALAUDIT"
    assert envs.get_env("test").leave_dispatch_closed_after is True
    assert envs.get_env("dev").leave_dispatch_closed_after is False


def test_unknown_env_rejected():
    with pytest.raises(ValueError):
        envs.get_env("prod")


@pytest.mark.parametrize("name", ["ADR-PROD-X", "x-master-y", "foo_security", "SENSITIVE1",
                                  "civileza-prod", "civileza-mpa", "adr-prod"])
def test_sensitive_profiles(name):
    assert envs.is_sensitive_profile(name)


@pytest.mark.parametrize("name", ["ADR-DEV-MEDICALAUDIT", "ADR-TEST-MEDICALAUDIT"])
def test_non_sensitive_profiles(name):
    assert not envs.is_sensitive_profile(name)


def test_asm_exec_command_shape():
    cmd = envs.asm_exec_command(envs.get_env("dev"), ["uv", "run", "launch.py"])
    assert cmd[:3] == ["env", "AWS_PROFILE=ADR-DEV-MEDICALAUDIT", "AWS_REGION=us-east-1"]
    assert cmd[3:5] == ["asm-exec", "--"]
    assert cmd[5:7] == ["env",
                        "IAE_CLIENT_SECRET={{resolve:secretsmanager:adr-dev-medicalaudit-scriptconnection:SecretString:secretapi}}"]
    assert cmd[7:] == ["uv", "run", "launch.py"]


def test_expected_audience():
    assert envs.expected_audience("test") == "adr-test-medicalaudit-intelligent-audit-engine-api"


def test_asm_exec_command_uses_resolved_invocation(monkeypatch):
    monkeypatch.setattr(envs, "resolve_asm_exec", lambda: ["python3", "/x/asm-exec"])
    cmd = envs.asm_exec_command(envs.get_env("dev"), ["a"])
    assert cmd[3:6] == ["python3", "/x/asm-exec", "--"]


def test_asm_exec_command_explicit_override_and_fallback(monkeypatch):
    monkeypatch.setattr(envs, "resolve_asm_exec", lambda: None)
    assert envs.asm_exec_command(envs.get_env("dev"), ["a"])[3] == "asm-exec"
    assert envs.asm_exec_command(envs.get_env("dev"), ["a"], asm=["zz"])[3] == "zz"


def _write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_find_asm_exec_prefers_working_path_binary(tmp_path):
    good = _write(tmp_path / "bin" / "asm-exec", "... aws___run_script ...")
    assert envs.find_asm_exec(which=lambda n: str(good), home=tmp_path) == [str(good)]


def test_find_asm_exec_skips_outdated_and_uses_newest_plugin_copy(tmp_path):
    old = _write(tmp_path / "bin" / "asm-exec", "aws___call_aws")
    ref = "agent-toolkit-for-aws/aws-core/{}/skills/aws-secrets-manager/references/asm-exec"
    base = tmp_path / ".claude" / "plugins" / "cache"
    a = _write(base / ref.format("1.2.0"), "aws___run_script")
    b = _write(base / ref.format("1.10.0"), "aws___run_script")
    c = _write(base / ref.format("1.11.0"), "aws___call_aws")  # desactualizado: se descarta
    assert envs.find_asm_exec(which=lambda n: str(old), home=tmp_path) == ["python3", str(b)]
    assert a != b != c


def test_find_asm_exec_none(tmp_path):
    assert envs.find_asm_exec(which=lambda n: None, home=tmp_path) is None
