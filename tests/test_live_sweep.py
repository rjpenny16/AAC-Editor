"""Single-fault sweep for live TD Snap edits (roadmap B10, doc 05 Tier 2).

For each operation and each step index, inject each fault once against the
scripted fake in fake_tdsnap.py and assert what doc 04 requires:

- the outcome class matches the page: ``refused`` and ``rolled_back`` leave
  the page exactly as it was; ``verified`` leaves exactly what was asked;
- Undo is never pressed more times than the edit wrote, and never reaches
  into the user's earlier history when the outcome claims success or a
  verified restoration;
- nothing is pressed after a dialog appears;
- a batch never continues past an outcome other than verified or refused.

Then a seeded random-timing pass: random stale reads and failures from a
seed, the seed printed on failure, so every run is reproducible.
"""

import random

import pytest

from tdsnap import errors, live
from tdsnap.errors import PagesetError
from tests.fake_tdsnap import FakeTDSnap, install

START = {0: ("apple", None), 1: ("pear", "I want a pear"), 3: ("milk", None)}

OPERATIONS = {
    "add": dict(items=[{"label": "plum", "slot": 2, "symbol": False}]),
    "add_two": dict(items=[{"label": "plum", "slot": 2, "symbol": False},
                           {"label": "fig", "slot": 4, "message": "a fig", "symbol": False}]),
    "change": dict(changes=[{"slot": 0, "label": "apples"}]),
    "remove": dict(removals=[3]),
    "move": dict(moves=[{"slot": 0, "to": 5}]),
    "mixed": dict(items=[{"label": "plum", "slot": 2, "symbol": False}],
                  changes=[{"slot": 1, "label": "pears"}], removals=[3]),
}
FAULTS = ("fail", "crash", "dialog", "unreadable", "undo_disabled", "stale", "foreground_lost")


@pytest.fixture(autouse=True)
def _forget_last_edit():
    live.forget_last_edit()
    yield
    live.forget_last_edit()


def expected_page(operation):
    page = dict(START)
    spec = OPERATIONS[operation]
    for slot in spec.get("removals", []):
        page.pop(slot)
    for move in spec.get("moves", []):
        page[move["to"]] = page.pop(move["slot"])
    for change in spec.get("changes", []):
        _label, message = page[change["slot"]]
        page[change["slot"]] = (change["label"], message)
    for item in spec.get("items", []):
        page[item["slot"]] = (item["label"], item.get("message"))
    return page


def run(monkeypatch, operation, schedule):
    fake = FakeTDSnap(START, schedule)
    install(monkeypatch, fake)
    spec = OPERATIONS[operation]
    try:
        report = live.apply_page_edits(
            "Eating", spec.get("items", []), spec.get("changes", []),
            spec.get("removals", []), spec.get("moves", []), "v1",
        )
    except Exception as error:
        return fake, None, error
    return fake, report, None


def check_invariants(fake, report, error, operation, context):
    labels = lambda page: {slot: value[0] for slot, value in page.items()}  # noqa: E731
    assert fake.undo_presses <= fake.writes, (context, "Undo pressed more than the edit wrote")
    assert fake.inputs_after_dialog == 0, (context, "input sent after a dialog opened")
    assert fake.inputs_without_foreground == 0, (context, "input sent to another window")
    assert fake.edit_mode is False or getattr(error, "still_in_edit_mode", False), (
        context, "left in edit mode without saying so")
    if report is not None:
        assert report["outcome"] in (errors.VERIFIED, errors.VERIFIED_WITH_GAPS), context
        assert labels(fake.page) == labels(expected_page(operation)), context
        assert fake.damaged == 0, context
        return
    assert isinstance(error, PagesetError), (context, f"raw {type(error).__name__} escaped")
    outcome = errors.outcome_of(error)
    assert outcome in errors.OUTCOMES, context
    if outcome == errors.REFUSED:
        assert fake.writes == 0, (context, "refused, but something was written")
        assert labels(fake.page) == labels(START), context
    elif outcome == errors.ROLLED_BACK:
        assert labels(fake.page) == labels(START), (context, "claimed rolled back, page differs")
        assert fake.damaged == 0, (context, "rolled back into the user's earlier work")
    else:
        # partial / unknown: honest, and the batch stop rule must fire.
        assert live._batch_stop(error), context
        assert error.page_touched is True, context


def sweep_cases():
    for operation in OPERATIONS:
        for fault in FAULTS:
            for step in range(1, 14):
                yield operation, fault, step


@pytest.mark.parametrize(("operation", "fault", "step"), list(sweep_cases()))
def test_single_fault_sweep(monkeypatch, operation, fault, step):
    fake, report, error = run(monkeypatch, operation, {step: fault})
    check_invariants(fake, report, error, operation, (operation, fault, step))


@pytest.mark.parametrize("operation", list(OPERATIONS))
def test_a_clean_run_verifies_and_writes_exactly_the_plan(monkeypatch, operation):
    fake, report, error = run(monkeypatch, operation, {})
    assert error is None, error
    check_invariants(fake, report, error, operation, operation)
    assert fake.undo_presses == 0


@pytest.mark.parametrize("operation", list(OPERATIONS))
def test_a_failure_with_done_failing_too_keeps_its_outcome(monkeypatch, operation):
    """L10 across every operation: exit_fails never replaces the outcome."""
    for step in range(1, 10):
        fake, report, error = run(monkeypatch, operation, {step: "fail", "exit": "exit_fails"})
        if report is not None:
            continue
        check_invariants(fake, report, error, operation, (operation, step))
        if errors.outcome_of(error) != errors.REFUSED or fake.edit_mode:
            assert "still in edit mode" in str(error) or not fake.edit_mode


@pytest.mark.parametrize("seed", range(200))
def test_seeded_random_timing(monkeypatch, seed):
    """Random stale reads and failures from a seed; reproducible from the seed."""
    rng = random.Random(seed)  # noqa: S311 - reproducible test schedule, not security
    operation = rng.choice(list(OPERATIONS))
    schedule = {}
    for step in range(1, 16):
        roll = rng.random()
        if roll < 0.08:
            schedule[step] = "stale"
        elif roll < 0.12:
            schedule[step] = "fail"
        elif roll < 0.14:
            schedule[step] = "unreadable"
    fake, report, error = run(monkeypatch, operation, schedule)
    check_invariants(fake, report, error, operation, f"seed={seed} {operation} {schedule}")


def test_a_batch_never_continues_past_a_page_it_could_not_finish(monkeypatch):
    """Page B's rollback hits an unreadable page; the batch stops there with
    an honest outcome, keeps A's result, and never touches C."""
    calls = []
    real_apply = live.apply_page_edits

    def page_edit(page, *args, **kwargs):
        calls.append(page)
        fake = FakeTDSnap(START, {4: "fail", 5: "unreadable"} if page == "B" else {})
        install(monkeypatch, fake)
        monkeypatch.setattr(live, "apply_page_edits", page_edit)
        return real_apply("Eating", *args, **kwargs)

    monkeypatch.setattr(live, "apply_page_edits", page_edit)
    batch = live.apply_batch([
        {"page": name, "items": [{"label": "x", "slot": 2}], "fingerprint": "v1"}
        for name in ("A", "B", "C")
    ])
    statuses = [result["status"] for result in batch["results"]]
    assert statuses == ["applied", "failed", "skipped"]
    assert batch["results"][1]["outcome"] in (errors.UNKNOWN, errors.PARTIAL)
    assert calls == ["A", "B"]
