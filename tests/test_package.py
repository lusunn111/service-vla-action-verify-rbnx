import os
from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_and_contract_are_catalog_ready():
    manifest = yaml.safe_load((ROOT / "package_manifest.yaml").read_text())
    package = manifest["package"]
    assert package["name"] == "robonix.service.vla.action_verify"
    assert package["version"] == "0.1.0"
    assert package["license"] == "MulanPSL-2.0"
    assert "service" in package["tags"]
    assert manifest["capabilities"] == [
        {
            "name": "robonix/service/vla/action_verify/verify",
            "path": "capabilities/verify.v1.toml",
        }
    ]
    contract = tomllib.loads((ROOT / "capabilities/verify.v1.toml").read_text())
    assert contract["contract"]["id"] == "robonix/service/vla/action_verify/verify"
    assert contract["contract"]["kind"] == "service"
    assert contract["mode"]["type"] == "rpc"
    assert (ROOT / "capabilities/lib/action_verify/srv/Verify.srv").is_file()


def test_package_scripts_are_executable():
    for name in ("build.sh", "start.sh", "stop.sh"):
        path = ROOT / "scripts" / name
        assert path.is_file()
        assert os.access(path, os.X_OK)


def test_public_identity_contains_no_forwarding_skill():
    checked = [
        ROOT / "package_manifest.yaml",
        ROOT / "config.spec",
        ROOT / "CAPABILITY.md",
        ROOT / "vla_action_service/main.py",
        ROOT / "capabilities/verify.v1.toml",
    ]
    combined = "\n".join(path.read_text() for path in checked)
    assert "robonix.skill" not in combined
    assert "Skill(" not in combined
    assert "9010" not in combined
