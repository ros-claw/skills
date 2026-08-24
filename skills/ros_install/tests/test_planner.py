"""Unit tests for the ros_install 0.2.0 golden skill entrypoint.

These run in the skills repo CI with only pytest — no rosclaw package, no
root, no network. Host facts are injected via the ``context`` dict and the
host probe is monkeypatched where needed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).parent.parent / "entrypoint.py"


@pytest.fixture()
def skill():
    spec = importlib.util.spec_from_file_location("ros_install_entrypoint", ENTRYPOINT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CTX_NOBLE = {"os": "ubuntu", "os_version": "24.04", "arch": "amd64"}
CTX_JAMMY = {"os": "ubuntu", "os_version": "22.04", "arch": "arm64"}

# Every op type the golden plan may emit — must stay within the HostOps
# allowlist and never carry shell fields (doc §18/§19).
ALLOWED_OP_TYPES = {
    "package.install",
    "package.remove",
    "package.install_deb",
    "package.update",
    "repository.enable",
    "file.managed_write",
    "artifact.fetch",
}
FORBIDDEN_FIELDS = {"command", "shell", "script", "bash", "sh", "eval", "exec"}


def _clean_host(skill, monkeypatch):
    monkeypatch.setattr(
        skill,
        "collect_host_state",
        lambda ctx: {
            "ros_installed": False,
            "env_file_present": False,
            "rosdep_configured": False,
            "apt_source_present": False,
        },
    )


class TestDistroMatrix:
    def test_noble_maps_to_jazzy_desktop(self, skill, monkeypatch):
        _clean_host(skill, monkeypatch)
        plan = skill.plan(CTX_NOBLE, {})
        assert plan["target"]["ros_distro"] == "jazzy"
        assert plan["target"]["codename"] == "noble"
        packages = [
            p for op in plan["operations"] if op["type"] == "package.install" for p in op["packages"]
        ]
        assert "ros-jazzy-desktop" in packages
        # doc §39: the pub/sub verifier's graph packages are explicit deps.
        assert "ros-jazzy-demo-nodes-cpp" in packages
        assert "ros-jazzy-demo-nodes-py" in packages

    def test_jammy_maps_to_humble(self, skill, monkeypatch):
        _clean_host(skill, monkeypatch)
        plan = skill.plan(CTX_JAMMY, {})
        assert plan["target"]["ros_distro"] == "humble"
        packages = [
            p for op in plan["operations"] if op["type"] == "package.install" for p in op["packages"]
        ]
        assert "ros-humble-desktop" in packages

    def test_profiles(self, skill, monkeypatch):
        _clean_host(skill, monkeypatch)
        base = skill.plan(CTX_NOBLE, {"profile": "ros-base"})
        packages = [
            p for op in base["operations"] if op["type"] == "package.install" for p in op["packages"]
        ]
        assert "ros-jazzy-ros-base" in packages
        dev = skill.plan(CTX_NOBLE, {"profile": "development"})
        dev_packages = [
            p for op in dev["operations"] if op["type"] == "package.install" for p in op["packages"]
        ]
        assert "ros-dev-tools" in dev_packages

    def test_unsupported_os_fails_loudly(self, skill):
        with pytest.raises(ValueError, match="unsupported host"):
            skill.plan({"os": "debian", "os_version": "12", "arch": "amd64"}, {})

    def test_unsupported_arch_fails_loudly(self, skill):
        with pytest.raises(ValueError, match="unsupported architecture"):
            skill.plan({"os": "ubuntu", "os_version": "24.04", "arch": "riscv64"}, {})

    def test_unknown_profile_fails_loudly(self, skill, monkeypatch):
        _clean_host(skill, monkeypatch)
        with pytest.raises(ValueError, match="unknown profile"):
            skill.plan(CTX_NOBLE, {"profile": "everything"})


class TestOfficialAptSourceFlow:
    def test_uses_ros2_apt_source_not_raw_github(self, skill, monkeypatch):
        """doc §33/§52: keys/repos come from the ros2-apt-source deb —
        nothing is fetched from raw.githubusercontent.com at install time."""
        _clean_host(skill, monkeypatch)
        plan = skill.plan(CTX_NOBLE, {})
        fetch_ops = [op for op in plan["operations"] if op["type"] == "artifact.fetch"]
        assert len(fetch_ops) == 1
        url = fetch_ops[0]["url"]
        assert "github.com/ros-infrastructure/ros-apt-source/releases" in url
        assert "noble" in url
        assert "raw.githubusercontent.com" not in url
        # Every fetched artifact is digest-pinned (doc §12/§19).
        assert fetch_ops[0]["sha256"].startswith("sha256:")
        deb_ops = [op for op in plan["operations"] if op["type"] == "package.install_deb"]
        assert deb_ops and deb_ops[0]["artifact"] == fetch_ops[0]["name"]

    def test_existing_apt_source_skips_fetch(self, skill, monkeypatch):
        monkeypatch.setattr(
            skill,
            "collect_host_state",
            lambda ctx: {
                "ros_installed": False,
                "env_file_present": False,
                "rosdep_configured": False,
                "apt_source_present": True,
            },
        )
        plan = skill.plan(CTX_NOBLE, {})
        assert not [op for op in plan["operations"] if op["type"] == "artifact.fetch"]


class TestPlanSafety:
    def test_plan_ops_are_typed_and_shell_free(self, skill, monkeypatch):
        """doc §19/§53.4: the golden plan can never smuggle a shell."""
        _clean_host(skill, monkeypatch)
        plan = skill.plan(CTX_NOBLE, {})
        assert plan["domain"] == "host"
        for op in plan["operations"]:
            assert op["type"] in ALLOWED_OP_TYPES, op
            assert not (FORBIDDEN_FIELDS & set(op)), op


class TestExistingInstallRecovery:
    def test_installed_ros_yields_env_repair_only(self, skill, monkeypatch):
        """doc §37 Case A/B: do not reinstall; repair what is missing."""
        monkeypatch.setattr(
            skill,
            "collect_host_state",
            lambda ctx: {
                "ros_installed": True,
                "env_file_present": False,
                "rosdep_configured": True,
                "apt_source_present": True,
            },
        )
        plan = skill.plan(CTX_NOBLE, {})
        assert plan["note"] == "repair_existing_install"
        op_types = [op["type"] for op in plan["operations"]]
        assert "package.install" not in op_types
        assert op_types == ["file.managed_write"]

    def test_fully_healthy_install_is_noop_update(self, skill, monkeypatch):
        monkeypatch.setattr(
            skill,
            "collect_host_state",
            lambda ctx: {
                "ros_installed": True,
                "env_file_present": True,
                "rosdep_configured": True,
                "apt_source_present": True,
            },
        )
        plan = skill.plan(CTX_NOBLE, {})
        assert plan["operations"] == [{"type": "package.update"}]


class TestRecoveryMap:
    def test_network_failure_offers_opt_in_alternatives(self, skill):
        recovery = skill.recover(
            CTX_NOBLE, {"failed_op": {"type": "artifact.fetch", "error": "timeout"}}
        )
        assert recovery["action"] == "network_unavailable"
        assert "fishros_opt_in" in recovery["options"]
        assert "opt-in" in recovery["note"]

    def test_package_failure_suggests_dpkg_recovery(self, skill):
        recovery = skill.recover(CTX_NOBLE, {"failed_op": {"type": "package.install"}})
        assert recovery["action"] == "dpkg_recovery"

    def test_env_verification_failure_suggests_env_repair(self, skill):
        recovery = skill.recover(
            CTX_NOBLE, {"verification": {"ros_distro_env": "FAIL"}}
        )
        assert recovery["action"] == "repair_env"


class TestManifest:
    def test_manifest_declares_v2_execution_and_capability(self):
        import yaml

        manifest = yaml.safe_load(ENTRYPOINT.parent.joinpath("skill.yaml").read_text())
        assert manifest["schema_version"] == "rosclaw.skill.v2"
        assert manifest["capability"]["id"] == "environment.install.ros"
        assert manifest["execution"]["domain"] == "host"
        assert manifest["execution"]["planner"]["entrypoint"] == "entrypoint.py:plan"
        assert manifest["execution"]["verifier"]["entrypoint"] == "entrypoint.py:verify"
        assert manifest["safety"]["arbitrary_root_shell"] is False
        assert manifest["status"]["verification_status"] == "host_matrix_verified"
