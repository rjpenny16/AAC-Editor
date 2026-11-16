"""The local operation log (REL-025, roadmap A4).

The log exists so that one user report explains an intermittent failure. It
is only acceptable because of what it never contains, and only safe because
writing it can never affect an operation. Both are pinned here; the
seeded-label test across every error path is in test_privacy_contract.py.
"""

import json
import os

import pytest

from tdsnap import errors
from tdsnap.errors import PagesetError
from tdsnap.web import oplog, server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setattr(server, "_sessions", {})
    os.makedirs(server._SESSION_ROOT)
    return server.app.test_client()


def _records(folder):
    path = os.path.join(str(folder), "operations.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def test_records_keep_only_allow_listed_fields_and_code_like_values(_isolated_operation_log):
    oplog.record(kind="live.apply", outcome="verified", code="VERIFY_MISMATCH",
                 label="Apple juice", page="Breakfast Foods", path="C:\\Users\\x\\client.sps",
                 name="has spaces in it", counts={"add": 2, "Apple": "juice"})
    (item,) = _records(_isolated_operation_log)
    assert "label" not in item and "path" not in item
    # A page name is not a code: it never survives as itself.
    assert item["page"] == "?"
    assert item["name"] == "?"
    assert item["counts"] == {"add": 2}
    assert item["instance"] == oplog.INSTANCE
    assert "Apple" not in json.dumps(item) and "Breakfast" not in json.dumps(item)


def test_ident_is_stable_within_a_run_and_says_nothing_about_the_value():
    assert oplog.ident("Breakfast Foods") == oplog.ident("Breakfast Foods")
    assert oplog.ident("Breakfast Foods") != oplog.ident("Lunch")
    assert "Breakfast" not in oplog.ident("Breakfast Foods")


def test_logging_failures_never_reach_the_caller(monkeypatch):
    def broken(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(oplog, "_write", broken)
    oplog.record(kind="x")
    with oplog.operation("live.apply", "tdsnap") as op:
        op.step("select_cell")
        oplog.fallback("DB_LOCKED")
        oplog.note_undo()
    oplog.set_diagnostic(True)
    assert oplog.recent() == [] or isinstance(oplog.recent(), list)


def test_an_operation_records_outcome_code_duration_and_what_happened(_isolated_operation_log):
    with pytest.raises(PagesetError), oplog.operation("live.apply", "tdsnap") as op:
        oplog.count("add", 3)
        oplog.fallback("DB_LOCKED")
        oplog.note_undo()
        raise PagesetError("Apple could not be verified", code="VERIFY_MISMATCH",
                           outcome=errors.ROLLED_BACK, page_touched=True)
    (item,) = _records(_isolated_operation_log)
    assert item["op"] == op.id
    assert item["outcome"] == "rolled_back" and item["code"] == "VERIFY_MISMATCH"
    assert item["counts"] == {"add": 3} and item["fallbacks"] == ["DB_LOCKED"]
    assert item["undo_presses"] == 1 and item["exc"] == "PagesetError"
    assert isinstance(item["ms"], int)
    assert "Apple" not in json.dumps(item)


def test_steps_are_written_only_in_diagnostic_mode(_isolated_operation_log):
    with oplog.operation("live.apply") as op:
        op.step("select_cell", polls=3)
    assert [r for r in _records(_isolated_operation_log) if r["kind"] == "step"] == []

    oplog.set_diagnostic(True)
    assert oplog.diagnostic_status()["enabled"] is True
    with oplog.operation("live.apply") as op:
        op.step("select_cell", polls=3, foreground=True)
    steps = oplog.steps_for(op.id)
    assert [(s["name"], s["polls"], s["foreground"]) for s in steps] == [("select_cell", 3, True)]

    oplog.set_diagnostic(False)
    assert oplog.diagnostic_status()["enabled"] is False


def test_diagnostic_mode_switches_itself_off(monkeypatch):
    oplog.set_diagnostic(True)
    state = oplog._diagnostic_state()
    state["since"] -= (oplog.DIAGNOSTIC_HOURS + 1) * 3600
    with open(oplog._diagnostic_path(), "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    assert oplog.diagnostic_enabled() is False

    oplog.set_diagnostic(True)
    state = oplog._diagnostic_state()
    state["bytes"] = oplog.DIAGNOSTIC_BYTES
    with open(oplog._diagnostic_path(), "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    assert oplog.diagnostic_enabled() is False


def test_the_log_rotates_and_keeps_a_bounded_number_of_files(monkeypatch, _isolated_operation_log):
    monkeypatch.setattr(oplog, "MAX_BYTES", 300)
    for index in range(60):
        oplog.record(kind="x", step=index)
    names = sorted(os.listdir(_isolated_operation_log))
    assert "operations.jsonl" in names
    assert len([n for n in names if n.startswith("operations.jsonl")]) <= oplog.KEEP
    # Newest records are still readable, in order.
    assert [r["step"] for r in oplog.recent(3)] == [57, 58, 59]


def test_clear_deletes_the_log_and_diagnostic_state(_isolated_operation_log):
    oplog.set_diagnostic(True)
    oplog.record(kind="x")
    oplog.clear()
    assert [n for n in os.listdir(_isolated_operation_log)] == []


def test_server_operations_get_an_id_the_user_can_quote(client, _isolated_operation_log):
    token = {"X-TDSnap-Token": server.API_TOKEN}
    response = client.post("/api/pageset/missing-session/close", headers=token)
    op = response.headers.get("X-AAC-Op")
    assert op
    body = response.get_json()
    if response.status_code >= 400:
        assert body["op"] == op and body["code"] in errors.CODES
    records = [r for r in _records(_isolated_operation_log) if r.get("op") == op]
    assert len(records) == 1
    assert records[0]["kind"].startswith("post:pageset.x")
    assert "missing-session" not in json.dumps(records)


def test_a_refused_request_is_logged_with_its_code(client, _isolated_operation_log):
    token = {"X-TDSnap-Token": server.API_TOKEN}
    response = client.post("/api/pageset", headers=token, data={})
    assert response.status_code == 400
    body = response.get_json()
    assert body["outcome"] == "refused" and body["code"] == "REFUSED"
    record = next(r for r in _records(_isolated_operation_log) if r.get("op") == body["op"])
    assert record["outcome"] == "refused"


def test_a_stale_token_is_reported_as_such(client, _isolated_operation_log):
    response = client.post("/api/tdsnap/launch", headers={"X-TDSnap-Token": "old"})
    assert response.status_code == 403
    assert response.get_json()["code"] == "TOKEN_STALE"
    assert any(r.get("code") == "TOKEN_STALE" for r in _records(_isolated_operation_log))


def test_background_polls_and_autosave_are_not_logged(client, _isolated_operation_log):
    client.get("/api/health")
    client.get("/api/config")
    client.get("/api/settings")
    assert _records(_isolated_operation_log) == []


def test_errors_outcome_classification_defaults():
    assert errors.outcome_of(PagesetError("x")) == errors.REFUSED
    touched = PagesetError("x", page_touched=True)
    assert errors.outcome_of(touched) == errors.UNKNOWN
    assert errors.outcome_of(RuntimeError("COM")) == errors.UNKNOWN
    assert errors.code_of(RuntimeError("COM")) == "UNEXPECTED"
    assert errors.code_of(PagesetError("x", code="NOT_FOREGROUND")) == "NOT_FOREGROUND"
    assert errors.code_of(PagesetError("x", code="made up")) == "REFUSED"


# ---------------------------------------------------------------------------
# Intent journal (doc 04 L15, roadmap B4)


def test_an_edit_that_never_finished_is_reported_at_the_next_start(monkeypatch):
    oplog.journal_begin("aa11", "tdsnap", "post:tdsnap.edit-plan")
    oplog.journal_begin("bb22", "grid3", "post:grid3.edit-plan")
    oplog.journal_end("bb22", "verified")
    # The same run's unfinished edit is in progress, not interrupted.
    assert oplog.interrupted() == []

    monkeypatch.setattr(oplog, "INSTANCE", "next")
    found = oplog.interrupted()
    assert [(item["op"], item["app"]) for item in found] == [("aa11", "tdsnap")]
    assert isinstance(found[0]["at"], float)

    oplog.acknowledge_interrupted()
    assert oplog.interrupted() == []


def test_the_journal_never_names_a_page(_isolated_operation_log):
    oplog.journal_begin("cc33", "tdsnap", "Breakfast Foods page")
    text = open(os.path.join(str(_isolated_operation_log), "journal.jsonl"), encoding="utf-8").read()
    assert "Breakfast" not in text


def test_live_writes_are_journaled_and_reads_are_not(client, monkeypatch):
    from tdsnap import live

    began, ended = [], []
    monkeypatch.setattr(oplog, "journal_begin", lambda op, app, kind: began.append(kind))
    monkeypatch.setattr(oplog, "journal_end", lambda op, outcome: ended.append(outcome))
    monkeypatch.setattr(live, "apply_page_edits", lambda *a, **k: {
        "outcome": "verified", "page": "Eating", "checks": {}})
    monkeypatch.setattr(live, "last_edit", lambda: None)
    headers = {"X-TDSnap-Token": server.API_TOKEN, "X-TDSnap-Editor": "1"}
    client.post("/api/tdsnap/edit-plan", headers=headers, json={
        "operation": "edit_page", "page": "Eating", "fingerprint": "f",
        "items": [{"label": "apple", "slot": 0}]})
    assert began == ["post:tdsnap.edit-plan"] and ended == ["verified"]

    def boom(*_a, **_k):
        raise PagesetError("x", outcome="partial", page_touched=True)

    monkeypatch.setattr(live, "apply_page_edits", boom)
    client.post("/api/tdsnap/edit-plan", headers=headers, json={
        "operation": "edit_page", "page": "Eating", "fingerprint": "f",
        "items": [{"label": "apple", "slot": 0}]})
    assert ended[-1] == "partial"

    monkeypatch.setattr(live, "status", lambda *a, **k: {"running": False})
    client.get("/api/tdsnap/status", headers=headers)
    assert len(began) == 2


def test_the_interrupted_endpoints(client, monkeypatch):
    oplog.journal_begin("dd44", "tdsnap", "post:tdsnap.edit-plan")
    monkeypatch.setattr(oplog, "INSTANCE", "later")
    token = {"X-TDSnap-Token": server.API_TOKEN}
    assert client.get("/api/interrupted", headers=token).get_json()["edits"][0]["op"] == "dd44"
    client.post("/api/interrupted/ack", headers=token)
    assert client.get("/api/interrupted", headers=token).get_json()["edits"] == []


def test_a_write_can_be_asked_about_after_its_response_was_lost(client, monkeypatch):
    """H-14 / roadmap C9."""
    from tdsnap import live

    monkeypatch.setattr(live, "apply_page_edits", lambda *a, **k: {"outcome": "verified"})
    monkeypatch.setattr(live, "last_edit", lambda: None)
    headers = {"X-TDSnap-Token": server.API_TOKEN, "X-TDSnap-Editor": "1",
               "X-AAC-Request": "req-0001-abcd"}
    client.post("/api/tdsnap/edit-plan", headers=headers, json={
        "operation": "edit_page", "page": "Eating", "fingerprint": "f",
        "items": [{"label": "apple", "slot": 0}]})
    token = {"X-TDSnap-Token": server.API_TOKEN}
    result = client.get("/api/operation-result/req-0001-abcd", headers=token).get_json()
    assert result["known"] and result["done"] and result["outcome"] == "verified"
    assert result["succeeded"] is True and result["ok"] is True
    assert client.get("/api/operation-result/never-sent-1", headers=token).get_json()["known"] is False
    assert client.get("/api/operation-result/bad id!", headers=token).status_code in (400, 404)
