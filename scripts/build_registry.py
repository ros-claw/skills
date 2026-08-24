#!/usr/bin/env python3
"""Build registry/skills.json from the skills/ directory."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
REGISTRY_DIR = ROOT / "registry"
REGISTRY_FILE = REGISTRY_DIR / "skills.json"


def sha256_dir(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if not p.is_file():
            continue
        if ".git" in p.parts or "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        h.update(str(p.relative_to(path)).encode())
        h.update(p.read_bytes())
    return "sha256:" + h.hexdigest()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> int:
    REGISTRY_DIR.mkdir(exist_ok=True)
    skills: list[dict] = []

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_yaml = skill_dir / "skill.yaml"
        if not skill_yaml.exists():
            continue

        data = load_yaml(skill_yaml)
        metadata = data.get("metadata", {})
        identity = data.get("identity", {})
        status = data.get("status", {})

        name = metadata.get("name")
        namespace = metadata.get("namespace", "ros-claw")
        full_name = f"{namespace}/{name}"

        item = {
            "name": full_name,
            "display_name": metadata.get("display_name", name),
            "version": metadata.get("version"),
            "description": metadata.get("description", ""),
            "category": metadata.get("category", "general"),
            "robot_types": data.get("hub", {}).get("robot_types", ["universal"]),
            "compatible_robots": data.get("hub", {}).get("compatible_robots", ["universal"]),
            "tags": metadata.get("tags", []),
            "official": True,
            "installable": status.get("installable", True),
            "verification_status": status.get("verification_status", "official_verified"),
            "source": {
                "type": "github_subdir",
                "repo": identity.get("git_repo", "https://github.com/ros-claw/skills"),
                "ref": identity.get("git_ref", "main"),
                "subdir": identity.get("source_subdir", f"skills/{name}"),
            },
            "files": {
                "skill_yaml": f"skills/{name}/skill.yaml",
                "skill_md": f"skills/{name}/SKILL.md",
                "readme": f"skills/{name}/README.md",
            },
            "checksums": {
                "package_sha256": sha256_dir(skill_dir),
            },
        }
        skills.append(item)

    registry = {
        "schema_version": "rosclaw.skills_registry.v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_repo": "https://github.com/ros-claw/skills",
        "skills": skills,
    }

    REGISTRY_FILE.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {REGISTRY_FILE} with {len(skills)} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
