from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.main import create_app
from app.models.evaluation import BugVariant, EvalDataset, SeededBug
from app.services.evaluation_seed import DEMO_DATASET_ID, seed_demo_dataset


def _patch_hash(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _create_project_and_snapshot(client: TestClient, project_root) -> dict:
    project = client.post("/api/v1/projects", json={"name": "eval demo", "local_path": str(project_root)}).json()
    response = client.post(f"/api/v1/projects/{project['id']}/snapshots", json={"root_path": str(project_root)})
    assert response.status_code == 200
    return response.json()


def test_eval_dataset_task_bug_variant_api_enforces_patch_unique_hit(tmp_path, clean_db):
    app = create_app()
    project_root = tmp_path / "proj"
    package = project_root / "shop"
    package.mkdir(parents=True)
    (package / "pricing.py").write_text(
        "def shipping_fee(weight_kg):\n"
        "    if weight_kg <= 5:\n"
        "        return 10\n"
        "    return 20\n",
        encoding="utf-8",
    )

    with TestClient(app) as client:
        snapshot = _create_project_and_snapshot(client, project_root)

        dataset_response = client.post(
            "/api/v1/eval-datasets",
            json={
                "id": "dataset-api-v2",
                "name": "api dataset",
                "version": "v2",
                "project_snapshot_ids": [snapshot["id"]],
            },
        )
        assert dataset_response.status_code == 200
        dataset = dataset_response.json()

        duplicate = client.post(
            "/api/v1/eval-datasets",
            json={"name": "api dataset", "version": "v2", "project_snapshot_ids": [snapshot["id"]]},
        )
        assert duplicate.status_code == 409

        duplicate_id = client.post(
            "/api/v1/eval-datasets",
            json={
                "id": dataset["id"],
                "name": "api dataset other name",
                "version": "v3",
                "project_snapshot_ids": [snapshot["id"]],
            },
        )
        assert duplicate_id.status_code == 409

        task = client.post(
            f"/api/v1/eval-datasets/{dataset['id']}/tasks",
            json={
                "id": "task-api-v2",
                "project_snapshot_id": snapshot["id"],
                "target_scope": {"targets": ["shipping_fee"]},
                "goal": "cover shipping boundary",
                "expected_capabilities": ["boundary_value"],
            },
        ).json()
        duplicate_task_id = client.post(
            f"/api/v1/eval-datasets/{dataset['id']}/tasks",
            json={
                "id": task["id"],
                "project_snapshot_id": snapshot["id"],
                "goal": "duplicate task id",
            },
        )
        assert duplicate_task_id.status_code == 409

        bug = client.post(
            f"/api/v1/eval-tasks/{task['id']}/seeded-bugs",
            json={
                "id": "bug-shipping-boundary",
                "bug_type": "boundary",
                "description": "5kg boundary is wrong",
                "expected_detection": "assert shipping_fee(5) == 10",
            },
        ).json()
        duplicate_bug_id = client.post(
            f"/api/v1/eval-tasks/{task['id']}/seeded-bugs",
            json={
                "id": bug["id"],
                "bug_type": "boundary",
                "description": "duplicate bug id",
                "expected_detection": "duplicate",
            },
        )
        assert duplicate_bug_id.status_code == 409

        variant_response = client.post(
            f"/api/v1/seeded-bugs/{bug['id']}/variants",
            json={
                "id": "variant-shipping-boundary",
                "variant_name": "canonical patch",
                "patch": {
                    "file": "shop/pricing.py",
                    "old": "if weight_kg <= 5:",
                    "new": "if weight_kg < 5:",
                },
                "ground_truth": {"target": "shipping_fee"},
            },
        )
        assert variant_response.status_code == 200
        variant = variant_response.json()
        patch_payload = {
            "file": "shop/pricing.py",
            "old": "if weight_kg <= 5:",
            "new": "if weight_kg < 5:",
        }
        assert variant["patch_artifact_id"] is None
        assert variant["ground_truth"]["patch_unique_hit"]["hit_count"] == 1
        patch_artifact = variant["ground_truth"]["patch_artifact"]
        assert "uri" not in patch_artifact
        assert patch_artifact["storage"] == "inline"
        assert patch_artifact["content_id"].startswith("patch-")
        assert patch_artifact["content_hash"] == _patch_hash(patch_payload)
        assert patch_artifact["patch"] == patch_payload
        assert patch_artifact["metadata"]["relative_paths"] == ["shop/pricing.py"]

        duplicate_variant_id = client.post(
            f"/api/v1/seeded-bugs/{bug['id']}/variants",
            json={
                "id": variant["id"],
                "variant_name": "duplicate variant id",
                "patch": patch_payload,
            },
        )
        assert duplicate_variant_id.status_code == 409

        bad_mutated_root = project_root / "bad_mutated"
        bad_mutated_package = bad_mutated_root / "shop"
        bad_mutated_package.mkdir(parents=True)
        (bad_mutated_package / "pricing.py").write_text(
            "def shipping_fee(weight_kg):\n"
            "    if weight_kg <= 5:\n"
            "        return 10\n"
            "    return 20\n",
            encoding="utf-8",
        )
        bad_mutated_snapshot = client.post(
            f"/api/v1/projects/{snapshot['project_id']}/snapshots",
            json={"root_path": str(bad_mutated_root)},
        ).json()
        bad_mutated_variant = client.post(
            f"/api/v1/seeded-bugs/{bug['id']}/variants",
            json={
                "variant_name": "bad mutated snapshot",
                "mutated_snapshot_id": bad_mutated_snapshot["id"],
                "patch": patch_payload,
            },
        )
        assert bad_mutated_variant.status_code == 400
        assert "does not match canonical patch" in bad_mutated_variant.text

        bad_variant = client.post(
            f"/api/v1/seeded-bugs/{bug['id']}/variants",
            json={
                "variant_name": "bad patch",
                "patch": {
                    "file": "shop/pricing.py",
                    "old": "not present",
                    "new": "still absent",
                },
            },
        )
        assert bad_variant.status_code == 400
        assert "exactly once" in bad_variant.text

        detail = client.get(f"/api/v1/eval-datasets/{dataset['id']}").json()
        assert detail["tasks"][0]["seeded_bugs"][0]["variants"][0]["id"] == variant["id"]


def test_seed_demo_dataset_is_repeatable_and_keeps_patch_metadata(clean_db):
    with Session(get_engine()) as session:
        first = seed_demo_dataset(session)
        second = seed_demo_dataset(session)

        assert first["dataset_id"] == DEMO_DATASET_ID
        assert second["created_bugs"] == 0
        assert second["created_variants"] == 0

        dataset_count = session.scalar(select(func.count()).select_from(EvalDataset))
        bug_count = session.scalar(select(func.count()).select_from(SeededBug))
        variant_count = session.scalar(select(func.count()).select_from(BugVariant))

        assert dataset_count == 1
        assert bug_count == first["seeded_bug_count"]
        assert variant_count == first["seeded_bug_count"]

        variant = session.scalar(select(BugVariant).where(BugVariant.id == "variant-cmp-flip-discount"))
        assert variant is not None
        assert variant.patch_artifact_id is None
        assert variant.ground_truth["patch_unique_hit"]["hit_count"] == 1
        assert variant.ground_truth["patch_artifact"]["artifact_type"] == "bug_patch"
        assert variant.ground_truth["patch_artifact"]["storage"] == "inline"
        assert variant.ground_truth["patch_artifact"]["content_id"].startswith("patch-")
        assert "uri" not in variant.ground_truth["patch_artifact"]


def test_seed_demo_dataset_prevalidates_patches_before_writing(monkeypatch, clean_db):
    from eval.demo import bugs as demo_bugs

    bad_bug = replace(demo_bugs.BUGS[0], old="definitely not in clean source")
    monkeypatch.setattr(demo_bugs, "BUGS", [bad_bug])

    with Session(get_engine()) as session:
        with pytest.raises(ValueError, match="canonical patch must hit exactly once"):
            seed_demo_dataset(session)

        assert session.scalar(select(func.count()).select_from(EvalDataset)) == 0
        assert session.scalar(select(func.count()).select_from(SeededBug)) == 0
        assert session.scalar(select(func.count()).select_from(BugVariant)) == 0
