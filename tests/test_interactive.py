import io

import pytest

from bl.interactive import select_key


def test_select_key_with_no_default_ignores_enter(monkeypatch):
    # blank line (Enter) then EOF — with no default, Enter must not match
    # anything and the prompt should keep waiting until it runs out of input
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    with pytest.raises(EOFError):
        select_key("pick one:", [("a", "Option A", "A"), ("b", "Option B", "B")])


def test_select_key_with_none_as_the_default_value(monkeypatch):
    # this is the case the _NO_DEFAULT sentinel exists for: a default value
    # of None (e.g. an explicit "skip") must be distinguishable from "no
    # default was given at all"
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    result = select_key(
        "how long:", [("1", "a while", "a while"), ("0", "skip", None)], default=None
    )
    assert result is None


def test_select_key_explicit_key_still_works(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("b\n"))
    result = select_key("pick one:", [("a", "Option A", "A"), ("b", "Option B", "B")])
    assert result == "B"
