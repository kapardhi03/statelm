"""Cue tests. Cues decide what gets sampled, never what anything means."""

from __future__ import annotations

import pytest

import cues


class TestCorrectionCues:
    @pytest.mark.parametrize("text", [
        "actually make it 50", "sorry, I meant 45", "no wait, the other one",
        "scratch that", "rather than the first one", "my mistake",
    ])
    def test_hits(self, text):
        assert cues.has_correction_cue(text)

    @pytest.mark.parametrize("text", ["I want a 3BHK", "budget is 40 lakhs", ""])
    def test_misses(self, text):
        assert not cues.has_correction_cue(text)

    def test_a_substring_inside_a_word_is_not_a_cue(self):
        assert not cues.has_correction_cue("factually speaking")


class TestHedgeCues:
    @pytest.mark.parametrize("text", [
        "around 40 lakhs", "might stretch to 45", "roughly 2 crore",
        "up to 50", "at least 30", "not sure yet", "give or take a bit",
    ])
    def test_hits(self, text):
        assert cues.has_hedge_cue(text)

    @pytest.mark.parametrize("text", ["budget is 40 lakhs", "I will pay 50", ""])
    def test_misses(self, text):
        assert not cues.has_hedge_cue(text)


class TestStrata:
    def _turn(self, text, speaker="SPEAKER_1"):
        return {"text": text, "speaker_id": speaker}

    def test_plain_when_nothing_matches(self):
        assert cues.strata_for(self._turn("I want a 3BHK"), []) == frozenset({"plain"})

    def test_a_turn_can_be_in_two_strata(self):
        found = cues.strata_for(self._turn("actually around 45"), [])
        assert found == frozenset({"correction", "hedge"})

    def test_multi_speaker_needs_three_distinct_speakers(self):
        context = [self._turn("a", "SPEAKER_1"), self._turn("b", "SPEAKER_2")]
        turn = self._turn("plain text", "SPEAKER_3")
        assert "multi_speaker" in cues.strata_for(turn, context)

    def test_two_speakers_is_not_multi_speaker(self):
        context = [self._turn("a", "SPEAKER_1")]
        turn = self._turn("plain text", "SPEAKER_2")
        assert "multi_speaker" not in cues.strata_for(turn, context)

    def test_distinct_speakers_ignores_blanks(self):
        rows = [{"speaker_id": "SPEAKER_1"}, {"speaker_id": ""}, {"speaker_id": None}]
        assert cues.distinct_speakers(rows) == 1

    def test_plain_is_never_combined_with_a_real_stratum(self):
        found = cues.strata_for(self._turn("maybe 40"), [])
        assert "plain" not in found
