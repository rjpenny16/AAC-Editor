"""A scripted fake of one TD Snap page, with a fault schedule (roadmap B10).

Today's live tests replace the waits, the rollback and the verification with
the test itself, so a green live suite said nothing about the failure modes in
docs/reliability/03. This fake replaces only what touches Windows: the page,
its buttons, edit mode, TD Snap's Undo history and dialogs. The real
``apply_page_edits``, ``_failed_edit``, ``_restore_page_state``,
``_verify_final_layout``, ``apply_batch`` and outcome logic run against it.

Model
-----
- ``page`` maps a slot to ``(label, message)``.
- Every UI write the app makes pushes one entry on TD Snap's undo history;
  that is the assumption session T3-1 checks. ``prior_history`` entries model
  the user's own earlier work already on the history: undoing one of those is
  the over-undo the doc warns about, recorded in ``damaged``.
- ``schedule`` maps a step number to a fault. Steps count every write and
  every read of the page, so each run is repeatable.

Faults
------
``fail``             the step raises a PagesetError (an automation step failed)
``crash``            the step raises a raw RuntimeError (a COM error)
``dialog``           a dialog opens at the step, which then fails
``unreadable``       from this step on the page cannot be read
``exit_fails``       pressing Done fails
``undo_disabled``    Undo is disabled from this step on
``foreground_lost``  another window takes the foreground from this step on
``stale``            the step's write happens, but for the next STALE_SECONDS of
                     virtual time reads still show the page as it was before
                     (TD Snap has not repainted yet)

Time is virtual: ``time.sleep`` in live.py advances ``clock`` instead of
waiting, so a run takes no real time and every schedule is repeatable.
"""

from types import SimpleNamespace

from tdsnap import live
from tdsnap.errors import PagesetError

GRID = live.Grid((10, 20, 30), (40, 50), 8, 8)  # 3 x 2
# How long a repaint can lag behind a write. T3-1 experiment 4 measures the
# real figure; live.SETTLE_SECONDS must stay above it.
STALE_SECONDS = 0.25


class FakeTDSnap:
    def __init__(self, page, schedule=None, prior_history=2):
        self.page = dict(page)
        self.baseline = dict(page)
        self.history = [("prior", None)] * prior_history
        self.schedule = dict(schedule or {})
        self.step = 0
        self.edit_mode = False
        self.dialog = False
        self.unreadable = False
        self.undo_disabled = False
        self.undo_presses = 0
        self.writes = 0
        self.damaged = 0
        self.inputs_after_dialog = 0
        self.clock = 0.0
        self.foreground = True
        self.inputs_without_foreground = 0
        self.stale_until = -1.0
        self.stale_snapshot = {}

    # -- the clock of the schedule ------------------------------------------
    def tick(self, write=False):
        self.step += 1
        fault = self.schedule.get(self.step)
        if fault == "unreadable":
            self.unreadable = True
        elif fault == "undo_disabled":
            self.undo_disabled = True
        elif fault == "foreground_lost":
            self.foreground = False
        elif fault == "dialog":
            self.dialog = True
            raise PagesetError("TD Snap showed a message.")
        elif fault == "fail":
            raise PagesetError("TD Snap did not respond to the step.")
        elif fault == "crash":
            raise RuntimeError("(-2147220991, 'COM error')")
        elif fault == "stale" and write:
            self.stale_snapshot = dict(self.page)
            self.stale_until = self.clock + STALE_SECONDS
        if self.unreadable:
            raise OSError("COM: element not available")

    def write(self, slot, value):
        if self.dialog:
            self.inputs_after_dialog += 1
        self.tick(write=True)
        # The real helpers check the foreground before every raw input.
        live._require_foreground(None)
        if not self.foreground:
            self.inputs_without_foreground += 1
        self.history.append((slot, self.page.get(slot)))
        if value is None:
            self.page.pop(slot, None)
        else:
            self.page[slot] = value
        self.writes += 1

    # -- reads ---------------------------------------------------------------
    def shown(self):
        if self.clock < self.stale_until:
            return self.stale_snapshot
        return self.page

    def sleep(self, seconds):
        self.clock += max(0.0, float(seconds))

    def layout(self):
        self.tick()
        return [{"slot": slot, "label": label} for slot, (label, _m) in sorted(self.shown().items())]

    def fingerprint(self):
        if self.unreadable:
            raise OSError("COM: element not available")
        return tuple(sorted(self.shown().items()))

    # -- Undo ------------------------------------------------------------------
    def press_undo(self):
        if self.dialog:
            self.inputs_after_dialog += 1
        self.undo_presses += 1
        slot, before = self.history.pop()
        if slot == "prior":
            self.damaged += 1
            return
        if before is None:
            self.page.pop(slot, None)
        else:
            self.page[slot] = before


def install(monkeypatch, fake: FakeTDSnap):
    """Patch live.py's Windows-facing helpers onto *fake*."""
    group = SimpleNamespace()
    undo_button = SimpleNamespace(AutomationId="UndoButton")

    monkeypatch.setattr(live, "_desktop_unlocked", lambda: True)
    monkeypatch.setattr(live, "_automation", lambda: SimpleNamespace(DragDrop=None))
    monkeypatch.setattr(live, "_window", lambda _auto: object())
    monkeypatch.setattr(live, "_focus_window", lambda _w: None)
    monkeypatch.setattr(live, "_in_edit_mode", lambda _w: fake.edit_mode)
    monkeypatch.setattr(live, "_open_dialog", lambda _w: object() if fake.dialog else None)
    monkeypatch.setattr(live, "_page_name", lambda *_a: "Eating")
    monkeypatch.setattr(live, "_navigate_to_parent", lambda *_a: "Eating")
    monkeypatch.setattr(live, "_page_group", lambda _w: group)
    monkeypatch.setattr(live, "_fingerprint", lambda _g: fake.fingerprint())
    monkeypatch.setattr(live, "_fingerprint_token", lambda _g: "v1")
    monkeypatch.setattr(live, "_grid", lambda _g: GRID)
    monkeypatch.setattr(live, "_page_layout", lambda *_a: fake.layout())
    monkeypatch.setattr(live, "_visible_names", lambda _g: [])
    monkeypatch.setattr(live, "_stored_page_content", lambda _p, _n=(): {
        label: {"label": label, "message": message, "kind": "speak"}
        for label, message in fake.baseline.values()
    })
    monkeypatch.setattr(live, "_wait_for", _immediate)
    monkeypatch.setattr(live.time, "sleep", fake.sleep)

    def enter(_w):
        if fake.unreadable:
            raise OSError("COM: element not available")
        fake.edit_mode = True

    def leave(_w):
        if fake.schedule.get("exit") == "exit_fails" and fake.edit_mode:
            raise PagesetError("TD Snap did not leave edit mode.")
        fake.edit_mode = False

    monkeypatch.setattr(live, "_enter_edit_mode", enter)
    monkeypatch.setattr(live, "_exit_edit_mode", leave)

    def collapse(_w):
        if fake.unreadable:
            raise OSError("COM: element not available")

    monkeypatch.setattr(live, "_collapse_editor", collapse)

    def add(_auto, _w, cell, label, message=None, *_a, **_k):
        slot = GRID.xs.index(cell.x) + GRID.ys.index(cell.y) * len(GRID.xs) \
            if hasattr(cell, "x") else cell
        fake.write(slot, (label, message or None))
        if message:
            live._note_write("add")
            fake.history.append(("noop", None))
            fake.writes += 1
        return {"symbol": False, "symbol_source": None, "border": True}

    def slot_of(cell):
        return GRID.xs.index(cell.x) + GRID.ys.index(cell.y) * len(GRID.xs)

    def change(_auto, _w, cell, current, label=None, message=None):
        slot = slot_of(cell)
        old_label, old_message = fake.page.get(slot, (current, None))
        fake.write(slot, (label or old_label, old_message if message is None else (message or None)))

    def remove(_auto, _w, cell, _label, _message=None):
        fake.write(slot_of(cell), None)

    def move(_auto, _w, _grid, source, target, _label):
        value = fake.page.get(source)
        fake.write(target, value)
        live._note_write("move")
        fake.write(source, None)

    def require_foreground(_window):
        if not fake.foreground:
            raise PagesetError("TD Snap is not the window in front.", code="NOT_FOREGROUND")

    monkeypatch.setattr(live, "_require_foreground", require_foreground)
    monkeypatch.setattr(live, "_add_button", add)
    monkeypatch.setattr(live, "_change_button", change)
    monkeypatch.setattr(live, "_remove_button", remove)
    monkeypatch.setattr(live, "_move_button", move)

    def verify(_w, expected=(), removed=(), untouched=None):
        fake.tick()
        shown = fake.shown()
        for item in expected:
            if shown.get(item["slot"], (None, None))[0] != item["label"]:
                raise PagesetError(f"TD Snap did not verify {item['label']!r}.")
        for slot in removed:
            if slot in shown:
                raise PagesetError("TD Snap did not verify the removal.")
        for slot, label in (untouched or {}).items():
            if shown.get(slot, (None, None))[0] != label:
                raise PagesetError("TD Snap changed a button it was not meant to touch.")

    monkeypatch.setattr(live, "_verify_page_state", verify)

    def content_restored(_w, content):
        if fake.unreadable:
            raise OSError("COM: element not available")
        return all(
            fake.page.get(slot, (None, None))[0] == prior["label"]
            for slot, prior in (content or {}).items()
        )

    monkeypatch.setattr(live, "_content_restored", content_restored)

    def find(_root, **criteria):
        if criteria.get("automation_id") == "UndoButton":
            undo_button.IsEnabled = not fake.undo_disabled and bool(fake.history)
            return undo_button
        return None

    monkeypatch.setattr(live, "_find", find)
    monkeypatch.setattr(live, "_activate", lambda control: (
        fake.press_undo() if control is undo_button else None
    ))


def _immediate(callback, message, timeout=8, ignore=()):
    value = callback()
    if value:
        return value
    raise PagesetError(message)
