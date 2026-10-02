"""Detector tests. Expected spans are worked out by hand from the fabricated strings."""

from __future__ import annotations

import pytest

import detectors


def categories(text, roster=()):
    spans = detectors.resolve(detectors.find_all(text, roster))
    return {s.category for s in spans}


def redacted_text(text, roster=()):
    spans = detectors.redactions(detectors.resolve(detectors.find_all(text, roster)))
    return [(s.category, s.text) for s in spans]


class TestAmountRule:
    def test_a_bare_amount_is_never_redacted(self):
        # EXP-000's own labels turn on phrases like this; redacting them breaks the experiment.
        assert redacted_text("my budget is around 40 lakhs") == []

    def test_a_hedged_amount_survives(self):
        assert redacted_text("it might stretch to 45 lakhs") == []

    def test_an_account_linked_amount_is_redacted_with_the_account(self):
        got = redacted_text("transfer 40k to a/c 123456789012")
        assert ("ACCOUNT", "123456789012") in got
        assert any(c == "AMOUNT" for c, _ in got)

    def test_distance_decides(self):
        far = "budget is 40 lakhs. " + "x" * 200 + " a/c 123456789012"
        got = redacted_text(far)
        assert ("AMOUNT", "40 lakhs") not in got
        assert any(c == "ACCOUNT" for c, _ in got)


class TestStructuredIdentifiers:
    def test_email_and_upi_are_distinguished_by_the_dot(self):
        assert categories("desk@example.com") == {"EMAIL"}
        assert categories("priya@okaxis") == {"UPI"}

    def test_ifsc(self):
        assert "IFSC" in categories("IFSC HDFC0001234")

    def test_card_passing_luhn_beats_account(self):
        assert "CARD" in categories("card 4111111111111111")

    def test_luhn_rejects_a_near_miss(self):
        assert detectors.luhn_ok("4111111111111111")
        assert not detectors.luhn_ok("4111111111111112")

    def test_ten_digit_mobile_is_a_phone_not_an_account(self):
        assert categories("call 9876543210") == {"PHONE"}

    def test_phone_formats_all_detected(self):
        for raw in ("+91 98765 43210", "+91-9876543210", "09876543210", "9876543210"):
            assert "PHONE" in categories(raw), raw

    def test_transaction_reference(self):
        assert "TXNREF" in categories("UTR: ABCD12345678")


class TestAddresses:
    """The default is narrow on purpose: a locality is state, a premise number is an identifier."""

    def test_pincode_always(self):
        assert "ADDRESS" in categories("Bengaluru 560001")

    def test_a_locality_preference_survives_untouched(self):
        # "flat near Gachibowli" is a location preference the benchmark tracks, not PII.
        assert redacted_text("3BHK flat near Gachibowli, budget 80 lakhs") == []

    def test_a_flat_number_is_redacted_but_the_building_is_not(self):
        got = redacted_text("Flat 402, Sai Residency")
        assert got == [("ADDRESS", "402")]

    @pytest.mark.parametrize(
        "text,designator",
        [
            ("Flat 402", "402"),
            ("Flat No 402", "402"),
            ("Flat 4B", "4B"),
            ("H.No 3-4-12", "3-4-12"),
            ("House No 12", "12"),
            ("Plot 17", "17"),
            ("Door No 5", "5"),
            ("Villa 9", "9"),
        ],
    )
    def test_premise_designators(self, text, designator):
        assert redacted_text(text) == [("ADDRESS", designator)]

    def test_the_property_type_word_is_kept(self):
        spans = detectors.redactions(detectors.resolve(detectors.find_all("Flat 402")))
        assert all(s.text == "402" for s in spans)

    def test_a_hyphenated_word_is_not_a_premise_keyword(self):
        assert redacted_text("in-house 2 bedrooms") == []

    def test_a_keyword_without_a_number_is_not_an_address(self):
        assert redacted_text("looking for a plot somewhere") == []

    def test_locality_clauses_are_opt_in(self):
        without = detectors.find_addresses("Flat 4B, MG Road, there", clauses=False)
        assert [s.text for s in without] == ["4B"]
        with_clauses = detectors.find_addresses("Flat 4B, MG Road, there", clauses=True)
        assert any("MG Road" in s.text or s.text.startswith("Road") for s in with_clauses)


class TestNames:
    def test_roster_name_in_text(self):
        assert "PERSON" in categories("Hi, this is Priya Sharma.", ["Priya Sharma"])

    def test_first_name_alone_matches(self):
        assert "PERSON" in categories("Thanks Priya.", ["Priya Sharma"])

    def test_a_non_roster_name_is_not_detected(self):
        # Stated limit, not a bug: detection is roster-only by decision.
        assert "PERSON" not in categories("Thanks Rahul.", ["Priya Sharma"])

    def test_substring_inside_a_word_is_not_a_match(self):
        assert "PERSON" not in categories("priyanka is a word", ["Priya"])


class TestResolve:
    def test_higher_priority_wins_an_overlap(self):
        spans = detectors.resolve(detectors.find_all("priya@okaxis", ["priya"]))
        assert [s.category for s in spans] == ["UPI"]

    def test_result_is_ordered_and_non_overlapping(self):
        text = "desk@example.com and 9876543210 and a/c 123456789012"
        spans = detectors.resolve(detectors.find_all(text))
        assert spans == sorted(spans, key=lambda s: s.start)
        for a, b in zip(spans, spans[1:]):
            assert a.end <= b.start


class TestCanonicalNames:
    def test_a_first_name_hit_carries_its_roster_entry(self):
        spans = detectors.find_names("Thanks Priya.", ["Priya Sharma"])
        assert spans and all(s.canonical == "Priya Sharma" for s in spans)

    def test_a_full_name_hit_carries_the_same_entry(self):
        spans = detectors.find_names("this is Priya Sharma", ["Priya Sharma"])
        assert spans[0].canonical == "Priya Sharma"

    def test_non_person_spans_have_no_canonical(self):
        spans = detectors.find_at_handles("desk@example.com")
        assert spans[0].canonical is None
