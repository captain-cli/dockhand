import argparse
import json
from pathlib import Path

import pytest

from dockhand.manifest import load_applications_manifest


def project(tmp_path, *, inline=None, split=None):
    manifest = {"schema": "captain/manifest/v1", "project": {"name": "demo", "type": "application", "version": "1.0.0"}}
    if inline is not None:
        manifest["dockhand"] = inline
    if split is not None:
        manifest["manifests"] = {"dockhand": "manifests/dockhand.json"}
        (tmp_path / "manifests").mkdir()
        (tmp_path / "manifests/dockhand.json").write_text(json.dumps(split))
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


CONFIG = {"applications": [{"projectName": "demo", "applicationName": "api", "settingName": "port"}]}


def test_inline(tmp_path):
    assert load_applications_manifest(str(project(tmp_path, inline=CONFIG)), canonical=True) == CONFIG


def test_split(tmp_path):
    doc = {"schema": "captain/tool-manifest/v1", "tool": "dockhand", "config": CONFIG}
    assert load_applications_manifest(str(project(tmp_path, split=doc)), canonical=True) == CONFIG


def test_duplicate_sources_rejected(tmp_path):
    doc = {"schema": "captain/tool-manifest/v1", "tool": "dockhand", "config": CONFIG}
    project(tmp_path, inline=CONFIG, split=doc)
    with pytest.raises(Exception, match="both inline|both inline and"):
        load_applications_manifest(str(tmp_path), canonical=True)


def test_wrong_owner_rejected(tmp_path):
    doc = {"schema": "captain/tool-manifest/v1", "tool": "stager", "config": CONFIG}
    project(tmp_path, split=doc)
    with pytest.raises(Exception, match="belongs to"):
        load_applications_manifest(str(tmp_path), canonical=True)


def test_legacy_still_works(tmp_path):
    path = tmp_path / "dockhand.json"
    path.write_text(json.dumps(CONFIG))
    assert load_applications_manifest(str(path)) == CONFIG
