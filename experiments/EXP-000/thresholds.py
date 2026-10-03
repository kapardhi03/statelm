"""Every pre-registered number and measurement choice for EXP-000's agreement analysis.

Separated from the code that uses it so the pre-registered values are auditable in one place
and diffable on their own. Nothing here may change after a real run has been seen. If one must
change, the change is recorded in docs/research/experiments/EXP-000-label-feasibility.md with
the reason, per the repo's research rules.

Provenance of each value is named, because "who decided this and when" is the thing that makes
a pre-registration worth anything.
"""

from __future__ import annotations

#: The label vocabulary. Source: EXP-000's Setup section.
LABELS = (
    "NO-OP",
    "VALUE",
    "ABSTAIN:insufficient",
    "ABSTAIN:ambiguous",
    "ABSTAIN:conflicting",
    "HEDGED",
)

#: The three types the pre-registered threshold applies to. Source: EXP-000's Metric section,
#: "Cohen's κ per category. Working threshold κ ≥ 0.6 per abstention type." NO-OP is excluded
#: by ADR-003, which does not count it as abstention; VALUE and HEDGED are not abstention types.
ABSTENTION_TYPES = (
    "ABSTAIN:insufficient",
    "ABSTAIN:ambiguous",
    "ABSTAIN:conflicting",
)

#: Source: EXP-000's Metric section. The hypothesis is refuted if any abstention type is below it.
KAPPA_THRESHOLD = 0.6

#: Below this many items a category's κ is reported but marked "not interpretable", never
#: dropped or hidden. Counted as n_either: the number of items either rater assigned to the
#: category. Decided by Kapardhi, 2026-10-02 (Q3).
MIN_CATEGORY_N = 10

#: Bootstrap. The primary unit is the conversation, because turns within one chat are not
#: independent and an item-level resample would give a CI that is too narrow. Item-level is
#: computed too and reported as secondary, never as the headline.
#: Decided by Kapardhi, 2026-10-02 (Q1).
BOOTSTRAP_UNIT_PRIMARY = "conversation"
BOOTSTRAP_UNIT_SECONDARY = "item"
BOOTSTRAP_UNITS = (BOOTSTRAP_UNIT_PRIMARY, BOOTSTRAP_UNIT_SECONDARY)
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_CI_LEVEL = 0.95
BOOTSTRAP_SEED = 0

#: A replicate whose expected agreement is 1 has no defined κ (the denominator is zero). Such
#: replicates are excluded from the percentile interval and counted. Above this fraction the
#: interval itself is marked not interpretable, because it then describes only the subset of
#: resamples in which the category appeared. Decided by Kapardhi, 2026-10-02 (Q2).
UNDEFINED_REPLICATE_MAX_FRACTION = 0.05

#: Value agreement. Strict normalization is the primary figure; the number-aware pass is a
#: separate secondary figure and never replaces it. Decided by Kapardhi, 2026-10-02 (Q4).
VALUE_NORMALIZATION_PRIMARY = "strict"
VALUE_NORMALIZATION_SECONDARY = "number_aware"
VALUE_NORMALIZATIONS = (VALUE_NORMALIZATION_PRIMARY, VALUE_NORMALIZATION_SECONDARY)

#: Approximation markers. These change the *value*, so the number-aware pass records them as a
#: canonical flag rather than dropping them: "~40 lakhs" and "around 40 lakhs" are the same
#: value, and neither is "40 lakhs". Commitment words ("maybe", "might", "probably") are
#: deliberately absent, because under Kapardhi's Q1 decision of 2026-10-02 they change the
#: LABEL to HEDGED rather than the value, and should not appear in a VALUE at all.
APPROXIMATION_MARKERS = (
    "~", "around", "approx", "approximately", "about", "roughly", "circa", "ca", "ish",
)

#: Magnitude words the number-aware pass understands, as multipliers. "l" and "lac" are the
#: Indian-English spellings of lakh. Source: the pilot field list's budget field.
MAGNITUDES = {
    "thousand": 1_000,
    "k": 1_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "l": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
}

#: HEDGED carries the tentative value in the value column: "might stretch to 45" is labelled
#: HEDGED with value 45. This is rule (a), decided by Kapardhi on 2026-10-02 and provisional on
#: EXP-000's results. research-question.md lists hedged statements as Unresolved
#: ("Tentative value or abstain?"); this choice does not resolve that question, it fixes an
#: operational rule so annotation can proceed.
HEDGED_RULE = "a"
HEDGED_RULE_TEXT = (
    "HEDGED records the tentative value in the value column "
    '("might stretch to 45" -> label HEDGED, value 45).'
)

#: ADR-003 (typed abstention) is Proposed, not Accepted, and D4 is pending. EXP-000 is the
#: experiment that tests it, so everything above is provisional on a taxonomy that may change.
ADR_003_STATUS_AT_PREREGISTRATION = "Proposed"


#: Floating-point tolerance on the threshold comparison. A one-vs-rest table of
#: (both-in 2, a-only 1, b-only 1, both-out 14) has an exact kappa of 3/5, but computes as
#: 0.5999999999999996, so a bare `kappa >= 0.6` would report BELOW on a category that exactly
#: meets the threshold. n = 18 is well inside EXP-000's range, so this is reachable, not
#: theoretical. Added 2026-10-02, before any real run; a test pins that table.
KAPPA_TOLERANCE = 1e-9


def meets_threshold(kappa: float | None) -> bool | None:
    """Whether a kappa meets the pre-registered threshold. None in, None out.

    The tolerance admits a kappa that is exactly at the threshold in exact arithmetic but lands
    just under it in binary floating point. It is not a relaxation of the threshold: 0.6 minus
    anything a person would notice still reads as below.
    """
    if kappa is None:
        return None
    return kappa >= KAPPA_THRESHOLD - KAPPA_TOLERANCE


# ---------------------------------------------------------------------------- sampling
# Pre-registered 2026-10-02 after run 20261002T175103Z-f318529 was declared void by Kapardhi.
# That run produced no kappa, so none of this was chosen in the light of a result: there was no
# result. What it was chosen in the light of is a sampling failure, recorded in the experiment
# record's Change log.

#: A target turn must be the customer's. Seller turns and media placeholders remain in the
#: context window but are never the turn being labelled. Under the guideline's rule Q3 a
#: seller turn cannot establish a customer field, so a seller target is NO-OP by construction
#: and carries no information about whether annotators agree.
TARGET_ROLES = ("customer",)

#: Roles that are the seller side. Both map to "seller" in a sheet: the ARTHRYX schema cannot
#: tell a human takeover from the bot, which extract.yaml's role note states.
SELLER_ROLES = ("agent", "bot")

#: How a role is shown to an annotator. SPEAKER_n told them nothing about who was speaking,
#: which made rule Q3 unusable. Kapardhi's decision, 2026-10-02.
ROLE_DISPLAY = {"customer": "customer", "agent": "seller", "bot": "seller"}

#: Media rows reach the scrubbed text as "[media: ...]" placeholders; there is no kind column
#: downstream, so this prefix is the signal. A placeholder has no labellable content.
MEDIA_PLACEHOLDER_PREFIX = "[media:"

#: A target turn needs at least this many words. "ok", "yes" and a bare emoji cannot carry a
#: field value, so they produce NO-OP whatever the annotators think.
#: Kapardhi's decision, 2026-10-02.
MIN_TARGET_WORDS = 3

#: Enrichment quotas over the sampled turns. "random" is the remainder, drawn without a cue.
#: Kapardhi's decision, 2026-10-02. They sum to 1.0 on purpose.
SAMPLING_QUOTAS = {
    "field_mention": 0.4,
    "correction": 0.2,
    "hedge": 0.2,
    "random": 0.2,
}

#: The stratum name that means "no cue required"; filled last, from whatever is left.
RANDOM_STRATUM = "random"

#: Field-mention keywords, per pilot field. A match puts a turn in the field_mention stratum.
#: These steer *sampling only* and never appear in a sheet, so a false match costs a slightly
#: less enriched sample and cannot affect a label.
#:
#: Locality names are the weak spot: they are corpus-specific and cannot be enumerated here, so
#: location relies on indicator words and common Indian locality suffixes. `--field-keywords`
#: takes a local YAML file to extend any of these lists with real names from the corpus, which
#: keeps that text on the researcher's machine.
FIELD_KEYWORDS = {
    "budget": (
        "budget", "price", "cost", "afford", "lakh", "lakhs", "lac", "lacs", "crore", "crores",
        "cr", "loan", "emi", "down payment", "all inclusive", "negotiable", "rupees",
    ),
    "property_type": (
        "bhk", "flat", "apartment", "villa", "plot", "house", "duplex", "penthouse", "studio",
        "independent", "row house", "builder floor", "bungalow",
    ),
    "location_preference": (
        "near", "nearby", "close to", "locality", "area", "vicinity", "side", "zone",
        "metro", "highway", "school", "office",
    ),
    "timeline": (
        "possession", "ready", "immediately", "asap", "soon", "week", "weeks", "month",
        "months", "year", "years", "quarter", "handover", "move in", "shifting", "timeline",
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december", "diwali", "ugadi", "pongal",
    ),
    "decision_maker": (
        "wife", "husband", "spouse", "father", "mother", "dad", "mom", "parents", "brother",
        "sister", "son", "daughter", "family", "in-laws", "partner", "uncle", "aunt",
        "decide", "decides", "sign off", "approval", "discuss with", "check with",
    ),
}

#: A number followed by a magnitude word, which is how a budget is usually said. Kept separate
#: from the keyword lists because it is a pattern, not a word.
BUDGET_AMOUNT_FIELD = "budget"

#: Locality suffixes common in Indian place names, matched on a stem of at least three letters
#: so "bad" alone does not count.
LOCALITY_SUFFIXES = (
    "nagar", "puram", "halli", "pura", "pur", "abad", "guda", "palli", "wadi", "ganj",
    "colony", "layout", "enclave", "township", "vihar", "kunj", "garh",
)


#: Which item subset's verdict bears on ADR-003. Only the real one: the synthetic conversations
#: were authored by a model that knows the taxonomy and wrote the guideline, so agreement on
#: them measures whether two people can apply that guideline to text written against it.
#: Kapardhi's decision, 2026-10-03.
ADR_003_SUBSET = "real"
SYNTHETIC_VERDICT_NOTE = "guideline usability, not evidence for ADR-003"
REAL_VERDICT_NOTE = "bears on ADR-003"
COMBINED_VERDICT_NOTE = (
    "mixed real and synthetic items; reported for completeness and bears on ADR-003 no more "
    "than its synthetic share allows"
)
