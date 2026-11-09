"""The normalisers, which three measurements share.

If these drift, the templating ratio, the memory-dependence lower bound and the duplicate count all
move together and in ways that are hard to notice, so each rule is pinned here.
"""

from __future__ import annotations

from normalize import normalize_message, normalize_reply_template, stable_hash, word_count


def test_message_casefolds_and_collapses_whitespace():
    assert normalize_message("  Hello   THERE ") == "hello there"


def test_message_strips_punctuation():
    assert normalize_message("ok!!! thanks.") == "ok thanks"


def test_message_keeps_digits():
    """Collapsing them would make distinct messages look repeated and inflate measurement D."""
    assert normalize_message("budget 40") != normalize_message("budget 50")
    assert "40" in normalize_message("budget 40")


def test_message_normalises_unicode_width():
    assert normalize_message("ｈｅｌｌｏ") == "hello"


def test_message_handles_empty_and_none_like():
    assert normalize_message("") == ""
    assert normalize_message("   ") == ""


def test_reply_template_collapses_digit_runs():
    """The opposite rule to messages: two replies differing only in a number are one template."""
    assert normalize_reply_template("visit at 4 pm") == normalize_reply_template("visit at 11 pm")
    assert "#" in normalize_reply_template("visit at 4 pm")


def test_reply_template_still_separates_different_wording():
    assert normalize_reply_template("visit at 4 pm") != normalize_reply_template("call at 4 pm")


def test_stable_hash_is_stable_and_short():
    assert stable_hash("abc") == stable_hash("abc")
    assert len(stable_hash("abc")) == 12


def test_stable_hash_separates_different_text():
    assert stable_hash("abc") != stable_hash("abd")


def test_stable_hash_does_not_contain_the_input():
    assert "abc" not in stable_hash("abc")


def test_word_count():
    assert word_count("one two  three") == 3
    assert word_count("") == 0
    assert word_count("   ") == 0
