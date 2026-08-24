"""ros_install 0.2.0 — the first Golden Host Skill (doc §32-§39, §49).

All ROS domain knowledge lives HERE, not in ROSClaw Core: the distro
matrix, the official ros2-apt-source flow, the verification procedure and
the recovery map. Upgrading ROS support means upgrading this skill, never
the core runtime.

Design rules (doc §19/§33):
- The planner emits **typed HostOps only** — no shell, no curl|bash, no
  raw.githubusercontent key download (the ros2-apt-source deb manages the
  repository AND the keyring).
- FishROS-style remote scripts are an explicit operator opt-in recovery
  path, never the default.
- Installation success is defined by the verifier (doc §38/§39), never by
  "apt exited 0".

Stdlib-only: the entrypoint runs inside the ROSClaw runner process.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Skill data (doc §35): upgrade ROS support by upgrading THIS skill.
# ---------------------------------------------------------------------------

SKILL_REF = "ros-claw/ros_install@0.2.0"

DISTRO_MATRIX = {
    ("ubuntu", "24.04"): {"distro": "jazzy", "codename": "noble"},
    ("ubuntu", "22.04"): {"distro": "humble", "codename": "jammy"},
}

SUPPORTED_ARCHES = {"amd64", "arm64", "x86_64", "aarch64"}

# Official ROS 2 repository management (doc §33): the ros2-apt-source deb
# installs the repository + keyring — no raw.githubusercontent key fetch.
APT_SOURCE_VERSION = "1.2.0"
APT_SOURCE_URL = (
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/"
    f"{APT_SOURCE_VERSION}/ros2-apt-source_{APT_SOURCE_VERSION}.{{codename}}_all.deb"
)
# Digests pinned at skill release time (verify with `curl -sL <url> | sha256sum`).
APT_SOURCE_SHA256 = {
    "noble": "sha256:0804d9b13db770eb87019be414cd78378835228ad5fa801fc88758596dd8f7e5",
    "jammy": "sha256:767884cf4ed03116b9d64438930a832ed854147ae435279a7924dfdf60f94433",
}
APT_SOURCE_ARTIFACT = "ros2-apt-source.deb"

PROFILES = {
    "desktop": ["ros-{distro}-desktop"],
    "ros-base": ["ros-{distro}-ros-base"],
    "development": ["ros-{distro}-desktop", "ros-dev-tools"],
}

ROSDEP_SOURCES = """\
# os-specific listings first
yaml https://raw.githubusercontent.com/ros/rosdistro/master/rosdep/osx-homebrew.yaml osx

# generic
yaml https://raw.githubusercontent.com/ros/rosdistro/master/rosdep/base.yaml
yaml https://raw.githubusercontent.com/ros/rosdistro/master/rosdep/python.yaml
yaml https://raw.githubusercontent.com/ros/rosdistro/master/rosdep/ruby.yaml
gbpdistro https://raw.githubusercontent.com/ros/rosdistro/master/releases/fuerte.yaml fuerte
"""

ENV_FILE_PATH = "/etc/profile.d/rosclaw-ros.sh"


# ---------------------------------------------------------------------------
# HostState (doc §34): probed by the planner on the real host.
# ---------------------------------------------------------------------------


def collect_host_state(context: dict) -> dict:
    os_id = str(context.get("os", ""))
    os_version = str(context.get("os_version", ""))
    arch = str(context.get("arch", ""))
    entry = DISTRO_MATRIX.get((os_id, os_version), {})
    distro = entry.get("distro", "")
    opt_ros = Path(f"/opt/ros/{distro}") if distro else None
    return {
        "os": os_id,
        "version": os_version,
        "arch": arch,
        "distro": distro,
        "codename": entry.get("codename", ""),
        "ros_installed": bool(opt_ros and (opt_ros / "bin" / "ros2").exists()),
        "env_file_present": Path(ENV_FILE_PATH).exists(),
        "rosdep_configured": Path("/etc/ros/rosdep/sources.list.d/20-default.list").exists(),
        "apt_source_present": Path("/etc/apt/sources.list.d/ros2.list").exists(),
        "ros_distro_env": os.environ.get("ROS_DISTRO", ""),
    }


# ---------------------------------------------------------------------------
# Planner (doc §20/§34-§37): typed operations only.
# ---------------------------------------------------------------------------


def plan(context: dict, args: dict) -> dict:
    os_id = str(context.get("os", ""))
    os_version = str(context.get("os_version", ""))
    arch = str(context.get("arch", ""))

    if (os_id, os_version) not in DISTRO_MATRIX:
        supported = ", ".join(f"{o} {v}" for o, v in sorted(DISTRO_MATRIX))
        raise ValueError(
            f"unsupported host: {os_id} {os_version}; supported: {supported}. "
            f"Upgrade the ros_install skill to add new targets (doc §35)."
        )
    if arch not in SUPPORTED_ARCHES:
        raise ValueError(f"unsupported architecture: {arch}")

    entry = DISTRO_MATRIX[(os_id, os_version)]
    distro, codename = entry["distro"], entry["codename"]
    profile = str((args or {}).get("profile", "desktop"))
    if profile not in PROFILES:
        raise ValueError(
            f"unknown profile {profile!r}; choose from {sorted(PROFILES)} (doc §36)"
        )

    host = collect_host_state(context)
    operations: list[dict] = []

    if host["ros_installed"]:
        # Case A/B recovery-shaped plan (doc §37): ROS is already installed —
        # repair only what is missing instead of reinstalling everything.
        if not host["env_file_present"]:
            operations.append(_env_file_op(distro))
        if not host["rosdep_configured"]:
            operations.append(_rosdep_file_op())
        if not operations:
            operations.append({"type": "package.update"})
        return _plan_envelope(context, distro, codename, profile, operations,
                              note="repair_existing_install")

    operations.append({"type": "package.update"})
    operations.append(
        {
            "type": "package.install",
            "packages": ["software-properties-common", "curl", "gnupg", "lsb-release"],
        }
    )
    operations.append({"type": "repository.enable", "repository": "universe"})
    if not host["apt_source_present"]:
        operations.append(
            {
                "type": "artifact.fetch",
                "name": APT_SOURCE_ARTIFACT,
                "url": APT_SOURCE_URL.format(codename=codename),
                "sha256": APT_SOURCE_SHA256[codename],
            }
        )
        operations.append(
            {"type": "package.install_deb", "artifact": APT_SOURCE_ARTIFACT}
        )
    operations.append({"type": "package.update"})
    operations.append(
        {
            "type": "package.install",
            "packages": [p.format(distro=distro) for p in PROFILES[profile]],
        }
    )
    operations.append({"type": "package.install", "packages": ["python3-rosdep"]})
    if not host["rosdep_configured"]:
        operations.append(_rosdep_file_op())
    operations.append(_env_file_op(distro))
    return _plan_envelope(context, distro, codename, profile, operations,
                          note="clean_install")


def _env_file_op(distro: str) -> dict:
    return {
        "type": "file.managed_write",
        "path": ENV_FILE_PATH,
        "content": (
            f"# Managed by {SKILL_REF} — do not edit between the markers.\n"
            f"if [ -f /opt/ros/{distro}/setup.sh ]; then\n"
            f"    . /opt/ros/{distro}/setup.sh\n"
            f"fi\n"
        ),
        "mode": "0644",
    }


def _rosdep_file_op() -> dict:
    return {
        "type": "file.managed_write",
        "path": "/etc/ros/rosdep/sources.list.d/20-default.list",
        "content": ROSDEP_SOURCES,
        "mode": "0644",
    }


def _plan_envelope(context, distro, codename, profile, operations, *, note) -> dict:
    return {
        "skill": SKILL_REF,
        "domain": "host",
        "target": {
            "os": context.get("os", ""),
            "version": context.get("os_version", ""),
            "codename": codename,
            "arch": context.get("arch", ""),
            "ros_distro": distro,
            "profile": profile,
        },
        "operations": operations,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Verifier (doc §38/§39): success means ROS actually works.
# ---------------------------------------------------------------------------


def verify(context: dict, receipt: dict) -> dict:
    host = collect_host_state(context)
    distro = host["distro"]
    checks: dict[str, str] = {}
    details: dict[str, str] = {}

    opt_ros = Path(f"/opt/ros/{distro}")
    checks["opt_ros"] = "PASS" if opt_ros.is_dir() else "FAIL"

    # All ROS checks run through the sourced environment: the ros2 CLI and
    # demo nodes are not importable/runnable without setup.sh (PYTHONPATH,
    # AMENT_PREFIX_PATH, PATH).
    source = f". /opt/ros/{distro}/setup.sh"
    rc, out = _run(["bash", "-c", f"{source} && ros2 --help"], timeout=30)
    checks["ros2_cli"] = "PASS" if rc == 0 else "FAIL"
    details["ros2_cli"] = out[-300:]

    rc, out = _run(
        ["bash", "-c", f"{source} && printf %s \"$ROS_DISTRO\""],
        timeout=30,
    )
    checks["ros_distro_env"] = "PASS" if rc == 0 and out.strip() == distro else "FAIL"

    rosdep_rc, _ = _run(["rosdep", "--version"], timeout=30)
    if rosdep_rc == 0 and host["rosdep_configured"]:
        checks["rosdep"] = "PASS"
    elif rosdep_rc == 0:
        checks["rosdep"] = "DEGRADED"
        details["rosdep"] = "rosdep present but sources not configured"
    else:
        checks["rosdep"] = "FAIL"

    pubsub_ok, pubsub_out = _verify_pubsub(distro)
    checks["dds_pubsub"] = "PASS" if pubsub_ok else "FAIL"
    details["dds_pubsub"] = pubsub_out[-300:]

    hard = ("opt_ros", "ros2_cli", "ros_distro_env", "dds_pubsub")
    verified = all(checks[k] == "PASS" for k in hard) and checks["rosdep"] in {
        "PASS",
        "DEGRADED",
    }
    return {**checks, "details": details, "result": "VERIFIED" if verified else "FAILED"}


def _verify_pubsub(distro: str) -> tuple[bool, str]:
    """doc §39: run a real ROS graph (talker + listener) and require messages."""
    source = f". /opt/ros/{distro}/setup.sh"
    talker = subprocess.Popen(
        ["bash", "-c", f"{source} && exec demo_nodes_cpp talker"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=_clean_env(),
    )
    try:
        listener = subprocess.run(
            ["bash", "-c", f"{source} && exec timeout 45 demo_nodes_py listener"],
            capture_output=True,
            text=True,
            timeout=60,
            env=_clean_env(),
        )
        output = listener.stdout + listener.stderr
        return ("I heard" in output), output
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    finally:
        talker.terminate()
        try:
            talker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            talker.kill()


def _clean_env() -> dict:
    """ROS commands need a pristine environment: a foreign PYTHONPATH or
    LD_LIBRARY_PATH (e.g. from a CI Python toolchain) breaks the ros2 CLI's
    importlib.metadata discovery and the demo nodes."""
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "LD_LIBRARY_PATH"):
        env.pop(key, None)
    return env


def _run(argv: list[str], *, timeout: int) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, env=_clean_env()
        )
        return completed.returncode, completed.stdout + completed.stderr
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 127, str(exc)


# ---------------------------------------------------------------------------
# Recovery (doc §37/§52): where a skill beats a generic agent.
# ---------------------------------------------------------------------------


def recover(context: dict, failure: dict) -> dict:
    failed_op = (failure or {}).get("failed_op") or {}
    op_type = str(failed_op.get("type", ""))
    error = str(failed_op.get("error", ""))
    verification = (failure or {}).get("verification") or {}

    # Case D (doc §52): network unreachable — do NOT loop; offer honest
    # alternatives. FishROS remote script only as explicit operator opt-in.
    if op_type == "artifact.fetch":
        return {
            "action": "network_unavailable",
            "options": [
                "retry_after_network_check",
                "manual_artifact_download",
                "docker_ros_image",
                "fishros_opt_in",
            ],
            "note": (
                "The default flow fetches ros2-apt-source from GitHub releases; "
                "it does NOT depend on raw.githubusercontent.com. Switching to "
                "the FishROS remote script requires explicit operator opt-in."
            ),
        }

    # Case C: apt/dpkg interrupted.
    if op_type.startswith("package."):
        return {
            "action": "dpkg_recovery",
            "note": (
                "run `sudo dpkg --configure -a` and `sudo apt-get -f install` "
                "via the operator TTY, then re-approve the regenerated plan; "
                "the plan hash will change and must be re-approved (doc §21)"
            ),
        }

    # Case A/B: verification failed on environment, not installation.
    if verification.get("ros_distro_env") == "FAIL":
        return {
            "action": "repair_env",
            "note": (
                "ROS is installed but the environment is not sourced; re-run "
                "the planner — it emits an env-repair-only plan for existing "
                "installations"
            ),
        }
    if verification.get("rosdep") in {"FAIL", "DEGRADED"}:
        return {
            "action": "rosdep_repair",
            "note": "re-run the planner to rewrite /etc/ros/rosdep sources",
        }

    return {"action": "manual_review", "note": "no automatic recovery mapped"}


__all__ = ["plan", "verify", "recover", "collect_host_state", "DISTRO_MATRIX"]
