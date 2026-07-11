from tdsnap import validate
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


def test_new_warnings_detection():
    before = {"problems": [], "warnings": ["existing"]}
    after = {"problems": [], "warnings": ["existing", "brand new"]}
    assert validate.new_warnings(before, after) == ["brand new"]
