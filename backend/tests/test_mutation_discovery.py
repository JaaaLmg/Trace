from app.services.mutation_discovery import discover_mutation_candidates


def test_mutation_discovery_dry_run_finds_boundary_candidates_and_samples_deterministically(tmp_path):
    project = tmp_path / "proj"
    package = project / "shop"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "pricing.py").write_text(
        "def shipping_fee(weight_kg):\n"
        "    if weight_kg <= 5:\n"
        "        return 10\n"
        "    if weight_kg >= 10:\n"
        "        return 30\n"
        "    return 20\n\n"
        "def untouched(value):\n"
        "    return value == 1\n",
        encoding="utf-8",
    )
    tests_dir = project / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_pricing.py").write_text(
        "def helper_test_target(value):\n"
        "    return value <= 5\n",
        encoding="utf-8",
    )

    result = discover_mutation_candidates(
        root=project,
        eval_task_id="task-pricing",
        source_snapshot_id="snap-clean",
        target_scope={"targets": ["shop.pricing.shipping_fee"]},
        sample_seed=7,
        max_selected=1,
    )
    repeat = discover_mutation_candidates(
        root=project,
        eval_task_id="task-pricing",
        source_snapshot_id="snap-clean",
        target_scope={"targets": ["shop.pricing.shipping_fee"]},
        sample_seed=7,
        max_selected=1,
    )

    assert result == repeat
    assert result.selected_count == 1
    assert result.excluded_count == 0
    assert len(result.candidates) == 2
    assert {candidate.patch.old for candidate in result.candidates} == {"weight_kg <= 5", "weight_kg >= 10"}
    assert {candidate.patch.new for candidate in result.candidates} == {"weight_kg < 5", "weight_kg > 10"}
    assert all(candidate.patch.file == "shop/pricing.py" for candidate in result.candidates)
    assert all(candidate.matcher.target_symbol == "shipping_fee" for candidate in result.candidates)
    selected = [candidate for candidate in result.candidates if candidate.selection.status == "selected"]
    assert selected[0].selection.sample_seed == 7
    assert selected[0].selection.sample_index == 0
    assert not any(candidate.patch.file.startswith("tests/") for candidate in result.candidates)


def test_mutation_discovery_dry_run_reports_exclusions_without_writing_variants(tmp_path):
    project = tmp_path / "proj"
    package = project / "shop"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "pricing.py").write_text(
        "def repeated(value):\n"
        "    if value <= 5:\n"
        "        return 1\n"
        "    if value <= 5:\n"
        "        return 2\n"
        "    return 3\n\n"
        "def chained(value, upper):\n"
        "    return 1 < value < upper\n\n"
        "def equality(value):\n"
        "    return value == 1\n",
        encoding="utf-8",
    )

    result = discover_mutation_candidates(
        root=project,
        eval_task_id="task-pricing",
        source_snapshot_id="snap-clean",
        target_scope={"targets": ["repeated", "chained", "equality", "missing_target"]},
        sample_seed=0,
        max_selected=10,
    )

    assert result.candidates == []
    reason_codes = [exclusion.reason_code for exclusion in result.exclusions]
    assert "non_unique_patch" in reason_codes
    assert reason_codes.count("unsupported_compare") == 2
    assert "target_not_found" in reason_codes
    assert result.excluded_count == len(result.exclusions)
    missing = [exclusion for exclusion in result.exclusions if exclusion.reason_code == "target_not_found"]
    assert missing[0].target_ref == "missing_target"
