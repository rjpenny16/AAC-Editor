"""Pinning tests for the shared UIA helper layer (tdsnap/uia.py).

Each reconciled divergence between the old tdsnap/live.py and tdsnap/grid3.py
implementations gets a test here — see uia.py's module docstring for the
reasoning behind each choice. This is the one place that behavior is tested;
live.py and grid3.py only need to prove they delegate to it correctly.
"""

from types import SimpleNamespace

import pytest

from tdsnap import uia
from tdsnap.errors import PagesetError

# ---------------------------------------------------------------------------
# walk()


def test_walk_default_depth_is_ten():
    """10 is a strict superset of TD Snap's old default of 9 (see docstring)."""
    assert uia.WALK_MAX_DEPTH == 10


def test_walk_visits_every_control_up_to_max_depth():
    def node(name, children=()):
        return SimpleNamespace(name=name, GetChildren=lambda: list(children))

    leaf = node("leaf")
    branch = node("branch", [leaf])
    root = node("root", [branch])

    depth_zero = [control.name for control, depth in uia.walk(root, max_depth=0)]
    assert depth_zero == ["root"]

    full = [control.name for control, depth in uia.walk(root, max_depth=5)]
    assert full == ["root", "branch", "leaf"]


def test_walk_skips_a_control_that_vanishes_mid_walk():
    """A control disappearing mid-walk (GetChildren raising) is skipped, not fatal."""
    def raises():
        raise RuntimeError("control is gone")

    root = SimpleNamespace(GetChildren=lambda: [
        SimpleNamespace(GetChildren=raises),
        SimpleNamespace(GetChildren=lambda: []),
    ])

    results = list(uia.walk(root, max_depth=3))

    # root + both depth-1 children are yielded; the one that raises on its own
    # GetChildren() just contributes no further descendants.
    assert len(results) == 3


# ---------------------------------------------------------------------------
# clusters()


def test_cluster_tolerance_is_eight():
    """Widened from grid3.py's unexplained 6 — see docstring for the reasoning."""
    assert uia.CLUSTER_TOLERANCE == 8


def test_cluster_tolerance_merges_points_grid3s_old_six_would_have_split():
    # A gap of 7: grid3.py's old tolerance of 6 would start a new group;
    # the reconciled tolerance of 8 keeps the two points together.
    values = [0, 7]
    assert uia.clusters(values, tolerance=6) == (0, 7)
    assert uia.clusters(values, tolerance=8) == (4,)  # round(mean([0, 7]))


def test_clusters_rounds_to_the_group_mean():
    assert uia.clusters([100, 102, 104, 300, 302]) == (102, 301)


def test_clusters_of_empty_input_is_empty():
    assert uia.clusters([]) == ()


# ---------------------------------------------------------------------------
# activate()


class _BusyThenOk:
    """An Invoke() pattern that raises the transient HRESULT once, then succeeds."""

    def __init__(self, failures=1, hresult=-2147220992):
        self.calls = 0
        self.failures = failures
        self.hresult = hresult

    def Invoke(self):
        self.calls += 1
        if self.calls <= self.failures:
            error = Exception("busy")
            error.hresult = self.hresult
            raise error


def test_activate_retries_only_the_transient_hresult(monkeypatch):
    monkeypatch.setattr(uia.time, "sleep", lambda _seconds: None)
    pattern = _BusyThenOk(failures=2)
    control = SimpleNamespace(GetInvokePattern=lambda: pattern)

    uia.activate(control)

    assert pattern.calls == 3


def test_activate_does_not_retry_a_different_error():
    class Boom:
        def Invoke(self):
            error = Exception("boom")
            error.hresult = -1
            raise error

    control = SimpleNamespace(GetInvokePattern=lambda: Boom())
    with pytest.raises(Exception, match="boom"):
        uia.activate(control)


def test_activate_gives_up_after_the_retry_deadline(monkeypatch):
    """Never-recovering busy control raises the product's busy_message."""
    ticks = iter([0, 0, uia.ACTIVATE_RETRY_SECONDS + 1])
    monkeypatch.setattr(uia.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(uia.time, "sleep", lambda _seconds: None)

    class AlwaysBusy:
        def Invoke(self):
            error = Exception("busy")
            error.hresult = -2147220992
            raise error

    control = SimpleNamespace(GetInvokePattern=lambda: AlwaysBusy())
    with pytest.raises(PagesetError, match="stayed busy too long"):
        uia.activate(control, busy_message="stayed busy too long")


def test_activate_falls_back_to_selection_then_click():
    selected = []
    no_invoke = SimpleNamespace(
        GetInvokePattern=lambda: None,
        GetSelectionItemPattern=lambda: SimpleNamespace(Select=lambda: selected.append(1)),
    )
    uia.activate(no_invoke)
    assert selected == [1]

    clicked = []
    plain = SimpleNamespace(
        GetInvokePattern=lambda: None,
        GetSelectionItemPattern=lambda: None,
        Click=lambda simulateMove: clicked.append(simulateMove),
    )
    uia.activate(plain)
    assert clicked == [False]


def test_activate_rejects_a_vanished_control():
    with pytest.raises(PagesetError, match="changed while the edit was running"):
        uia.activate(None, missing_message="changed while the edit was running")


# ---------------------------------------------------------------------------
# wait_for()


def test_wait_for_default_timeout_is_eight_seconds():
    """Matches grid3.py's old default; widening TD Snap's old 6s can only help."""
    assert uia.WAIT_DEFAULT_TIMEOUT == 8


def test_wait_for_returns_the_first_truthy_value(monkeypatch):
    monkeypatch.setattr(uia.time, "sleep", lambda _seconds: None)
    values = iter([None, False, "", "ready"])
    assert uia.wait_for(lambda: next(values), "never") == "ready"


def test_wait_for_raises_with_the_given_message_on_timeout(monkeypatch):
    ticks = iter([0, 0, 100])
    monkeypatch.setattr(uia.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(uia.time, "sleep", lambda _seconds: None)
    with pytest.raises(PagesetError, match="gave up"):
        uia.wait_for(lambda: None, "gave up", timeout=1)


def test_wait_for_ignore_swallows_only_named_exceptions(monkeypatch):
    monkeypatch.setattr(uia.time, "sleep", lambda _seconds: None)

    def flaky():
        flaky.calls += 1
        if flaky.calls == 1:
            raise KeyError("mid-write")
        return "done"

    flaky.calls = 0
    assert uia.wait_for(flaky, "never", ignore=(KeyError,)) == "done"

    def always_raises():
        raise KeyError("nope")

    with pytest.raises(KeyError):
        uia.wait_for(always_raises, "never")  # not ignored by default


# ---------------------------------------------------------------------------
# automation()


def test_automation_raises_platform_message_off_windows(monkeypatch):
    monkeypatch.setattr(uia.sys, "platform", "linux")
    with pytest.raises(PagesetError, match="only on Windows"):
        uia.automation("only on Windows", "missing")


# ---------------------------------------------------------------------------
# process identity helpers (only exercised off-Windows here; the Windows
# ctypes path is exercised implicitly by the live/grid3 E2E suites)


def test_process_helpers_return_none_off_windows(monkeypatch):
    monkeypatch.setattr(uia.sys, "platform", "linux")
    assert uia.process_app_user_model_id(1234) is None
    assert uia.process_image_path(1234) is None


def test_process_helpers_return_none_for_falsy_process_id():
    assert uia.process_app_user_model_id(0) is None
    assert uia.process_image_path(None) is None
