from placeholders import PlaceholderMap, normalize


class TestConsistency:
    def test_same_value_same_token(self):
        pmap = PlaceholderMap()
        assert pmap.token("PERSON", "Priya") == pmap.token("PERSON", "Priya")

    def test_different_values_different_tokens(self):
        pmap = PlaceholderMap()
        assert pmap.token("PERSON", "Priya") != pmap.token("PERSON", "Arthryx Desk")

    def test_numbered_by_first_appearance(self):
        pmap = PlaceholderMap()
        assert pmap.token("PHONE", "9876543210") == "[PHONE_1]"
        assert pmap.token("PHONE", "9000000000") == "[PHONE_2]"

    def test_phone_surface_variants_share_a_token(self):
        pmap = PlaceholderMap()
        first = pmap.token("PHONE", "+91 98765 43210")
        assert pmap.token("PHONE", "9876543210") == first

    def test_case_insensitive_for_text_categories(self):
        pmap = PlaceholderMap()
        assert pmap.token("EMAIL", "Desk@Example.com") == pmap.token("EMAIL", "desk@example.com")

    def test_counters_are_per_category(self):
        pmap = PlaceholderMap()
        assert pmap.token("PERSON", "Priya") == "[PERSON_1]"
        assert pmap.token("PHONE", "9876543210") == "[PHONE_1]"


class TestScope:
    def test_a_fresh_map_restarts_numbering(self):
        # Per-conversation scope: the same person is PERSON_1 in each conversation and cannot
        # be linked across them.
        first, second = PlaceholderMap(), PlaceholderMap()
        assert first.token("PERSON", "Priya") == second.token("PERSON", "Priya") == "[PERSON_1]"

    def test_tokens_are_not_hashes_of_the_original(self):
        pmap = PlaceholderMap()
        token = pmap.token("EMAIL", "desk@example.com")
        assert token == "[EMAIL_1]"
        assert "desk" not in token and "example" not in token


class TestNormalize:
    def test_short_phone_keeps_what_it_has(self):
        assert normalize("PHONE", "12345") == "12345"

    def test_other_categories_strip_only(self):
        assert normalize("ACCOUNT", " 123456789012 ") == "123456789012"


class TestEntries:
    def test_entries_report_original_and_token(self):
        pmap = PlaceholderMap()
        pmap.token("PERSON", "Priya")
        entry = pmap.entries()[0]
        assert (entry.category, entry.original, entry.token) == ("PERSON", "Priya", "[PERSON_1]")

    def test_index_of_is_none_before_assignment(self):
        assert PlaceholderMap().index_of("PERSON", "Nobody") is None


class TestCanonicalIdentity:
    def test_surface_variants_of_one_person_share_a_token(self):
        # scrub.py keys on span.canonical, which is what makes this hold end to end.
        pmap = PlaceholderMap()
        full = pmap.token("PERSON", "Priya Sharma")
        assert pmap.token("PERSON", "Priya Sharma") == full
