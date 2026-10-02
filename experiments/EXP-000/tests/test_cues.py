"""Cue tests. Cues decide what gets sampled, never what anything means."""

from __future__ import annotations

import pytest

import cues
import thresholds


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
        # "I want a 3BHK" was this test's example until field_mention existed; it now correctly
        # matches property_type, so the example has to be text that mentions no field at all.
        assert cues.strata_for(self._turn("please send me the documents"), []) \
            == frozenset({"plain"})

    def test_a_field_mention_is_not_plain(self):
        assert cues.strata_for(self._turn("I want a 3BHK"), []) \
            == frozenset({"field_mention"})

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


class TestTargetEligibility:
    """What can be a target at all. The distinction that voided run 20261002T175103Z-f318529."""

    def customer(self, text):
        return {"text": text, "speaker_role": "customer"}

    def test_a_seller_turn_is_never_a_target(self):
        for role in ("agent", "bot"):
            turn = {"text": "I can share the brochure with you today", "speaker_role": role}
            assert cues.target_rejection(turn) == "not_customer"
            assert not cues.is_eligible_target(turn)

    def test_a_customer_turn_of_real_text_is(self):
        assert cues.is_eligible_target(self.customer("budget is around 80 lakhs"))

    def test_a_media_placeholder_is_not(self):
        assert cues.target_rejection(self.customer("[media: voice note]")) == "media_placeholder"
        assert cues.target_rejection(self.customer("[media: image]")) == "media_placeholder"

    @pytest.mark.parametrize("text", ["ok", "yes", "yes ok", "", "   "])
    def test_a_turn_too_short_to_carry_a_value_is_not(self, text):
        assert cues.target_rejection(self.customer(text)) in {"too_short", "empty"}

    def test_three_words_is_the_floor(self):
        assert thresholds.MIN_TARGET_WORDS == 3
        assert cues.target_rejection(self.customer("one two")) == "too_short"
        assert cues.target_rejection(self.customer("one two three")) is None

    def test_the_reason_is_returned_not_just_a_bool(self):
        """The sampler reports why a corpus yields few targets, so the reason has to survive."""
        reasons = {
            cues.target_rejection({"text": "a long enough sentence here", "speaker_role": "agent"}),
            cues.target_rejection(self.customer("[media: video]")),
            cues.target_rejection(self.customer("ok")),
        }
        assert reasons == {"not_customer", "media_placeholder", "too_short"}


class TestRoleDisplay:
    def test_the_seller_side_collapses_to_one_word(self):
        assert cues.display_role({"speaker_role": "agent"}) == "seller"
        assert cues.display_role({"speaker_role": "bot"}) == "seller"
        assert cues.display_role({"speaker_role": "customer"}) == "customer"

    def test_an_unmapped_role_is_shown_not_coerced(self):
        """A schema that grows a third party must show up, not be absorbed into one side."""
        assert cues.display_role({"speaker_role": "broker"}) == "broker"
        assert cues.display_role({}) == "unknown"


class TestFieldMention:
    @pytest.mark.parametrize("text,field", [
        ("budget is 80 lakhs", "budget"),
        ("can we do 1.2 cr", "budget"),
        ("around 50k deposit", "budget"),
        ("looking for a 3BHK", "property_type"),
        ("a villa would suit us", "property_type"),
        ("plot is fine too", "property_type"),
        ("possession by March please", "timeline"),
        ("we want to move in next month", "timeline"),
        ("my wife has to agree", "decision_maker"),
        ("my brother will sign off", "decision_maker"),
        ("somewhere near the metro", "location_preference"),
        ("anything in Jayanagar", "location_preference"),
        ("prefer Kondapur", "location_preference"),
    ])
    def test_each_pilot_field_has_a_cue(self, text, field):
        assert field in cues.fields_mentioned(text), (text, sorted(cues.fields_mentioned(text)))

    def test_a_digit_glued_to_the_keyword_still_matches(self):
        """"3BHK" is the commonest spelling, and a word boundary will not match "bhk" there."""
        assert "property_type" in cues.fields_mentioned("3BHK")
        assert "property_type" in cues.fields_mentioned("want a 2bhk")

    def test_a_keyword_inside_a_longer_word_does_not_match(self):
        assert cues.fields_mentioned("abhk nonsense") == frozenset()
        assert "location_preference" not in cues.fields_mentioned("the purpose of the call")

    def test_small_talk_mentions_no_field(self):
        for text in ("thanks a lot", "good morning to you", "i will call you back"):
            assert cues.fields_mentioned(text) == frozenset(), text

    def test_keywords_can_be_overridden_for_locality_names(self):
        """Locality names are corpus-specific; the override is how they stay on one machine."""
        # "near Gachibowli" would match on the indicator word "near" regardless, so the text
        # here carries the locality name alone, which the built-in lists cannot know.
        assert "location_preference" not in cues.fields_mentioned("Gachibowli please")
        custom = {**thresholds.FIELD_KEYWORDS, "location_preference": ("gachibowli",)}
        assert "location_preference" in cues.fields_mentioned("Gachibowli please", custom)

    def test_an_override_cannot_invent_a_field(self):
        custom = {"budget": ("budget",)}
        assert cues.fields_mentioned("budget is 80 lakhs", custom) == frozenset({"budget"})


class TestCuesLookOnlyAtTheTargetTurn:
    """Pinned because the void run's cues appeared to match seller text.

    They did not: matching was always against the turn's own text. What made seller text drive
    selection was that seller turns were eligible targets. This asserts the property directly so
    a future change cannot quietly start reading the context.
    """

    SELLER_CONTEXT = [
        {"text": "Sorry, I meant the east-facing units", "speaker_role": "agent",
         "speaker_id": "SPEAKER_2"},
        {"text": "maybe around 1200 sq ft, budget friendly", "speaker_role": "agent",
         "speaker_id": "SPEAKER_2"},
    ]

    def test_a_plain_target_stays_plain_beside_cue_heavy_seller_context(self):
        target = {"text": "please send the documents", "speaker_role": "customer",
                  "speaker_id": "SPEAKER_1"}
        strata = cues.strata_for(target, self.SELLER_CONTEXT)
        assert "correction" not in strata
        assert "hedge" not in strata
        assert "field_mention" not in strata

    def test_the_targets_own_cues_do_count(self):
        target = {"text": "actually make it around 90 lakhs", "speaker_role": "customer",
                  "speaker_id": "SPEAKER_1"}
        strata = cues.strata_for(target, self.SELLER_CONTEXT)
        assert {"correction", "hedge", "field_mention"} <= strata

    def test_multi_speaker_is_the_one_stratum_that_reads_context(self):
        """And it carries no quota, so it cannot pull the sample toward anything."""
        target = {"text": "please send the documents", "speaker_role": "customer",
                  "speaker_id": "SPEAKER_1"}
        context = [*self.SELLER_CONTEXT, {"text": "hi", "speaker_role": "bot",
                                          "speaker_id": "SPEAKER_3"}]
        assert "multi_speaker" in cues.strata_for(target, context)
        assert "multi_speaker" not in thresholds.SAMPLING_QUOTAS
