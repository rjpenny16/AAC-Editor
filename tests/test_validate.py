from tdsnap import builder, validate
from tdsnap.builder import add_category_page


def _build(ps):
    parent_id = ps.find_page_id_by_name("Home Page")
    return add_category_page(ps, "Snacks", ["Chips", "Apple"], parent_id)


def test_clean_pageset_passes(seeded_pageset):
    result = validate.validate_pageset(seeded_pageset.conn)
    assert result == {"problems": [], "warnings": []}


def test_detects_orphaned_placement(seeded_pageset):
    ps = seeded_pageset
    report = _build(ps)
    # Orphan one of the new page's own placements.
    ps.conn.execute(
        "UPDATE ElementPlacement SET PageLayoutId = NULL WHERE "
        "ElementReferenceId = (SELECT ElementReferenceId FROM Button WHERE Id = ?)",
        (report["button_ids"][0],),
    )
    problems = validate.validate_pageset(ps.conn)["problems"]
    assert any("no PageLayout" in p for p in problems)
    assert validate.validate_new_page(ps.conn, report)  # chain check fails too


def test_detects_missing_command_sequence(seeded_pageset):
    ps = seeded_pageset
    report = _build(ps)
    ps.conn.execute(
        "DELETE FROM CommandSequence WHERE ButtonId = ?",
        (report["button_ids"][0],),
    )
    problems = validate.validate_pageset(ps.conn)["problems"]
    assert any("no CommandSequence" in p for p in problems)


def test_detects_broken_page_link(seeded_pageset):
    ps = seeded_pageset
    report = _build(ps)
    ps.conn.execute(
        "UPDATE ButtonPageLink SET PageUniqueId = 'ffffffff-0000-0000-0000-000000000000' "
        "WHERE ButtonId = ?",
        (report["nav_button_id"],),
    )
    result = validate.validate_pageset(ps.conn)
    assert any("not present in this file" in w for w in result["warnings"])
    # And the per-edit chain check names it as a hard failure:
    assert any(
        "ButtonPageLink" in p for p in validate.validate_new_page(ps.conn, report)
    )


def test_detects_button_spec_mismatch(seeded_pageset):
    """A built button that drifts from what was requested is named."""
    ps = seeded_pageset
    parent_id = ps.find_page_id_by_name("Home Page")
    report = add_category_page(
        ps, "Topic",
        [{"label": "Hi", "message": "Hello there!", "border_color": "#1E88E5"}],
        parent_id,
    )
    assert validate.validate_new_page(ps.conn, report) == []
    ps.conn.execute(
        "UPDATE Button SET Message = NULL, BorderColor = NULL WHERE Id = ?",
        (report["button_ids"][0],),
    )
    problems = validate.validate_new_page(ps.conn, report)
    assert any("speaks" in p for p in problems)
    assert any("border color" in p for p in problems)


def test_detects_sync_mismatch(seeded_pageset):
    ps = seeded_pageset
    report = _build(ps)
    ps.conn.execute(
        "UPDATE SyncData SET SyncHash = SyncHash + 1 WHERE UniqueId = ?",
        (report["page_unique_id"],),
    )
    assert any(
        "SyncData" in p for p in validate.validate_new_page(ps.conn, report)
    )


def test_detects_duplicate_grid_position(seeded_pageset):
    ps = seeded_pageset
    _build(ps)
    ps.conn.execute(
        "UPDATE ElementPlacement SET GridPosition = '0,0' WHERE Id = "
        "(SELECT MAX(Id) FROM ElementPlacement)"
    )
    problems = validate.validate_pageset(ps.conn)["problems"]
    assert any("more than one visible button" in p for p in problems)


def test_detects_spanning_overlap_and_invalid_geometry(seeded_pageset):
    ps = seeded_pageset
    ps.conn.execute(
        "UPDATE ElementPlacement SET GridSpan = '2,1' WHERE GridPosition = '0,0'"
    )
    problems = validate.validate_pageset(ps.conn)["problems"]
    assert any("more than one visible button" in problem for problem in problems)

    ps.conn.execute(
        "UPDATE ElementPlacement SET GridPosition = '-1,2', GridSpan = '0,1' "
        "WHERE GridPosition = '0,0'"
    )
    problems = validate.validate_pageset(ps.conn)["problems"]
    assert any("invalid grid position/span" in problem for problem in problems)


def test_roundtrip_guard(seeded_pageset):
    ps = seeded_pageset
    before = validate.table_snapshot(ps.conn)
    _build(ps)
    after = validate.table_snapshot(ps.conn)
    assert validate.check_roundtrip(before, after) == []
    # An edit that touches a forbidden table is caught:
    ps.conn.execute(
        "INSERT INTO VocabList (UniqueId, Name) "
        "VALUES ('99999999-9999-4999-8999-999999999999', 'rogue')"
    )
    tampered = validate.table_snapshot(ps.conn)
    assert validate.check_roundtrip(before, tampered)


def test_roundtrip_guard_rejects_unrelated_existing_row_changes(seeded_pageset):
    ps = seeded_pageset
    before = validate.table_snapshot(ps.conn)
    _build(ps)
    ps.conn.execute("UPDATE Page SET Title = 'Unintended' WHERE Title = 'Food'")
    after = validate.table_snapshot(ps.conn)

    problems = validate.check_roundtrip(before, after)
    assert any("unexpected columns: Title" in problem for problem in problems)


def test_roundtrip_guard_rejects_removed_allowed_table(seeded_pageset):
    before = validate.table_snapshot(seeded_pageset.conn)
    seeded_pageset.conn.execute("DROP TABLE ButtonPageLink")
    after = validate.table_snapshot(seeded_pageset.conn)

    problems = validate.check_roundtrip(before, after)
    assert any("Tables disappeared" in problem for problem in problems)


def test_roundtrip_guard_pairs_parent_page_and_syncdata(seeded_pageset):
    ps = seeded_pageset
    before = validate.table_snapshot(ps.conn)
    ps.conn.execute("UPDATE Page SET Timestamp = Timestamp + 1 WHERE Title = 'Food'")
    after = validate.table_snapshot(ps.conn)

    problems = validate.check_roundtrip(before, after)
    assert any("different pages" in problem for problem in problems)


def test_new_warnings_detection():
    before = {"problems": [], "warnings": ["existing"]}
    after = {"problems": [], "warnings": ["existing", "brand new"]}
    assert validate.new_warnings(before, after) == ["brand new"]


# ---------------------------------------------------------------------------
# Checking buttons added to a page that already existed (Phase 4c)


def _extend(ps, **overrides):
    page_id = ps.find_page_id_by_name("Home Page")
    layout = builder.layout_for_page(ps.conn, page_id, ps.grid_dimension())
    free = builder.free_slots(ps.conn, layout)
    return builder.add_buttons_to_page(
        ps, page_id, [{"label": "Chips", "slot": free[0], **overrides}]
    )


def test_added_buttons_pass_every_check_when_the_write_is_clean(seeded_pageset):
    report = _extend(seeded_pageset)
    assert validate.validate_added_buttons(seeded_pageset.conn, report) == []


def test_a_button_added_to_the_wrong_page_is_caught(seeded_pageset):
    ps = seeded_pageset
    report = _extend(ps)
    ps.conn.execute(
        "UPDATE ElementReference SET PageId = 999 WHERE Id = "
        "(SELECT ElementReferenceId FROM Button WHERE Id = ?)",
        (report["button_ids"][0],),
    )

    problems = validate.validate_added_buttons(ps.conn, report)
    assert any("not attached to the page" in problem for problem in problems)


def test_a_button_added_to_the_wrong_cell_is_caught(seeded_pageset):
    ps = seeded_pageset
    report = _extend(ps)
    slot = report["buttons"][0]["slot"]
    cols = report["grid"][0]
    ps.conn.execute(
        "UPDATE ElementPlacement SET GridPosition = '3,2' WHERE ElementReferenceId = "
        "(SELECT ElementReferenceId FROM Button WHERE Id = ?)",
        (report["button_ids"][0],),
    )

    problems = validate.validate_added_buttons(ps.conn, report)
    assert any(
        f"expected '{slot % cols},{slot // cols}'" in problem for problem in problems
    )


def test_a_cell_left_holding_two_buttons_is_caught(seeded_pageset):
    ps = seeded_pageset
    report = _extend(ps)
    slot = report["buttons"][0]["slot"]
    cols = report["grid"][0]
    # Something else made visible in the cell this button was placed in — the
    # one thing a placement-count check on the new button alone cannot see.
    other = ps.conn.execute("SELECT Id FROM ElementReference LIMIT 1").fetchone()[0]
    ps.conn.execute(
        "INSERT INTO ElementPlacement (GridPosition, GridSpan, Visible, "
        "ElementReferenceId, PageLayoutId) VALUES (?, '1,1', 1, ?, ?)",
        (f"{slot % cols},{slot // cols}", other, report["layout_id"]),
    )

    problems = validate.validate_added_buttons(ps.conn, report)
    assert any("more than one visible button" in problem for problem in problems)


def test_two_placements_for_one_added_button_are_caught(seeded_pageset):
    ps = seeded_pageset
    report = _extend(ps)
    reference = ps.conn.execute(
        "SELECT ElementReferenceId FROM Button WHERE Id = ?", (report["button_ids"][0],)
    ).fetchone()[0]
    ps.conn.execute(
        "INSERT INTO ElementPlacement (GridPosition, GridSpan, Visible, "
        "ElementReferenceId, PageLayoutId) VALUES ('3,2', '1,1', 1, ?, ?)",
        (reference, report["layout_id"]),
    )

    problems = validate.validate_added_buttons(ps.conn, report)
    assert any("2 placements; expected 1" in problem for problem in problems)


def test_a_placement_in_the_wrong_layout_or_without_a_span_is_caught(seeded_pageset):
    ps = seeded_pageset
    report = _extend(ps)
    # GridSpan is NOT NULL in the real schema, so a blank one is the shape this
    # check actually has to catch.
    ps.conn.execute(
        "UPDATE ElementPlacement SET PageLayoutId = 999, GridSpan = '' "
        "WHERE ElementReferenceId = "
        "(SELECT ElementReferenceId FROM Button WHERE Id = ?)",
        (report["button_ids"][0],),
    )

    problems = validate.validate_added_buttons(ps.conn, report)
    assert any("wrong page layout" in problem for problem in problems)
    assert any("missing GridSpan" in problem for problem in problems)


def test_a_missing_command_sequence_on_an_added_button_is_caught(seeded_pageset):
    ps = seeded_pageset
    report = _extend(ps)
    ps.conn.execute(
        "DELETE FROM CommandSequence WHERE ButtonId = ?", (report["button_ids"][0],)
    )

    problems = validate.validate_added_buttons(ps.conn, report)
    assert any("0 CommandSequence rows" in problem for problem in problems)


def test_content_that_disagrees_with_the_request_is_caught(seeded_pageset):
    ps = seeded_pageset
    report = _extend(ps, message="I want chips")
    ps.conn.execute(
        "UPDATE Button SET Label = 'Crisps', Message = NULL, UniqueId = 'not-a-guid' "
        "WHERE Id = ?",
        (report["button_ids"][0],),
    )

    problems = validate.validate_added_buttons(ps.conn, report)
    assert any("label is 'Crisps'" in problem for problem in problems)
    assert any("speaks None" in problem for problem in problems)
    assert any("no GUID UniqueId" in problem for problem in problems)


def test_a_missing_button_or_page_is_reported_rather_than_crashing(seeded_pageset):
    ps = seeded_pageset
    report = _extend(ps)
    ps.conn.execute("DELETE FROM Button WHERE Id = ?", (report["button_ids"][0],))
    assert any(
        "Requested button 'Chips' is missing" in problem
        for problem in validate.validate_added_buttons(ps.conn, report)
    )

    assert validate.validate_added_buttons(ps.conn, {**report, "page_id": 999}) == [
        "Page Id 999 is missing."
    ]
    assert validate.validate_added_buttons(ps.conn, {**report, "layout_id": 999}) == [
        "The layout the new buttons were placed in is missing."
    ]
