"""Opt-in settings store: written only on save, never blocks on a bad file."""

import json
import os

import pytest

from tdsnap.web import settings


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "_data_dir", lambda: str(tmp_path))
    return tmp_path


def test_fresh_install_writes_nothing_until_a_save(isolated_data_dir):
    assert not os.path.exists(settings.settings_path())
    data = settings.load()
    assert data == {"version": 1, "preferences": {}, "draft": None, "templates": []}
    assert not os.path.exists(settings.settings_path())  # a read never creates it


def test_save_then_load_roundtrips(isolated_data_dir):
    settings.save({"provider": "tdsnap"}, {"items": [{"label": "apple"}]})
    data = settings.load()
    assert data["preferences"] == {"provider": "tdsnap"}
    assert data["draft"] == {"items": [{"label": "apple"}]}
    assert os.path.exists(settings.settings_path())


def test_save_is_atomic_no_temp_file_left_behind(isolated_data_dir):
    settings.save({"provider": "grid3"}, None)
    leftovers = [name for name in os.listdir(isolated_data_dir) if name.startswith(".settings-")]
    assert leftovers == []


def test_corrupt_json_is_quarantined_and_treated_as_fresh(isolated_data_dir):
    path = settings.settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not valid json")

    data = settings.load()

    assert data == {"version": 1, "preferences": {}, "draft": None, "templates": []}
    assert not os.path.exists(path)
    quarantined = [name for name in os.listdir(isolated_data_dir) if "corrupt" in name]
    assert len(quarantined) == 1


def test_wrong_shape_is_quarantined(isolated_data_dir):
    path = settings.settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(["not", "an", "object"], handle)

    data = settings.load()

    assert data == {"version": 1, "preferences": {}, "draft": None, "templates": []}
    assert not os.path.exists(path)


def test_missing_preferences_key_is_quarantined(isolated_data_dir):
    path = settings.settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"version": 1}, handle)

    data = settings.load()

    assert data["preferences"] == {}
    assert not os.path.exists(path)


def test_oversized_file_is_quarantined_without_reading(isolated_data_dir, monkeypatch):
    path = settings.settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{}")
    monkeypatch.setattr(settings, "MAX_SETTINGS_BYTES", 1)

    data = settings.load()

    assert data == {"version": 1, "preferences": {}, "draft": None, "templates": []}
    assert not os.path.exists(path)


def test_clear_removes_the_file(isolated_data_dir):
    settings.save({"provider": "file"}, {"items": []})
    assert os.path.exists(settings.settings_path())
    settings.clear()
    assert not os.path.exists(settings.settings_path())


def test_clear_on_a_fresh_install_does_not_raise(isolated_data_dir):
    settings.clear()  # no file exists yet; must be a no-op, not an error


def test_draft_can_be_cleared_while_keeping_preferences(isolated_data_dir):
    settings.save({"provider": "tdsnap"}, {"items": [{"label": "apple"}]})
    settings.save({"provider": "tdsnap"}, None)
    data = settings.load()
    assert data["preferences"] == {"provider": "tdsnap"}
    assert data["draft"] is None


def _template(name="Swimming", label="Splash"):
    return {
        "name": name,
        "page_style": "topic",
        "saved_at": 1700000000,
        "items": [{"label": label, "message": None, "fn": "", "slot": None,
                   "symbol": True, "symbol_query": None}],
    }


def test_templates_roundtrip(isolated_data_dir):
    settings.save({}, None, [_template()])
    assert settings.load()["templates"] == [_template()]


def test_the_draft_autosave_cannot_wipe_saved_templates(isolated_data_dir):
    """The property `templates=None` exists to guarantee.

    The autosave PUTs preferences and draft every few seconds and says nothing
    about templates. A template is work the user deliberately named and
    expects to find later, so silence must mean "leave them alone".
    """
    settings.save({}, None, [_template()])
    settings.save({"provider": "tdsnap"}, {"items": [{"label": "pear"}]})
    data = settings.load()
    assert data["templates"] == [_template()]
    assert data["draft"] == {"items": [{"label": "pear"}]}


def test_templates_are_cleared_by_an_explicit_empty_list(isolated_data_dir):
    settings.save({}, None, [_template()])
    settings.save({}, None, [])
    assert settings.load()["templates"] == []


def test_a_file_written_before_templates_existed_still_loads(isolated_data_dir):
    """An older file is not a corrupt one: it loads, keeping its contents."""
    path = settings.settings_path()
    path_dir = os.path.dirname(path)
    os.makedirs(path_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "preferences": {"provider": "file"}, "draft": None}, handle)
    data = settings.load()
    assert data["preferences"] == {"provider": "file"}
    assert data["templates"] == []
    assert os.path.exists(path)  # not quarantined


def test_a_non_list_templates_key_is_ignored_rather_than_trusted(isolated_data_dir):
    path = settings.settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "preferences": {}, "draft": None, "templates": "nope"}, handle)
    assert settings.load()["templates"] == []
