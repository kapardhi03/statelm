"""Stage 2: the consent gate, the prompt freeze, the rungs, and Gate 2.

Every test here runs against the offline `StubBackend`. Nothing is uploaded, no key is needed, and
no credit is spent — which is the point: a pipeline that could only be tested by spending money and
sending client text would not get tested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import HEADER, item

from backends import Completion, StubBackend
from consent import Consent, ConsentError
from data import Item
from prompts import (
    PromptFreezeError,
    PromptTemplate,
    build_prompt,
    render_conversation,
    render_vocabulary,
    select_fewshot,
    sha256_text,
)
from rungs import LADDER, MODEL_RUNGS, Providers
from run_stage2 import extract_action, gate_two
from safety import assert_output_safe
from thresholds import FEWSHOT_K, MIN_EFFECT_PP

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


# --- the consent gate (Q9) -------------------------------------------------------------------------

def _consent_yaml(tmp_path: Path, **over) -> Path:
    body = {
        "instructed_on": "2026-11-09",
        "instruction_verbatim": "yes, upload the product-eval export to tinker and anthropic",
        "providers": ["tinker", "anthropic"],
        "data_slice": "the labelled product-eval export, dev and test",
    }
    body.update(over)
    lines = []
    for k, v in body.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            lines.extend(f"  - {x}" for x in v)
        else:
            lines.append(f"{k}: {v}")
    p = tmp_path / "consent.yaml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_missing_consent_file_is_refused(tmp_path):
    with pytest.raises(ConsentError, match="does not exist"):
        Consent.load(tmp_path / "nope.yaml")


def test_consent_requires_every_field(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("instructed_on: 2026-11-09\n", encoding="utf-8")
    with pytest.raises(ConsentError, match="required and unset"):
        Consent.load(p)


def test_consent_rejects_a_placeholder_instruction(tmp_path):
    """A record that shows someone ticked a box is not a record of what was authorised."""
    with pytest.raises(ConsentError, match="placeholder"):
        Consent.load(_consent_yaml(tmp_path, instruction_verbatim="ok"))


def test_consent_authorises_only_named_providers(tmp_path):
    c = Consent.load(_consent_yaml(tmp_path))
    c.require({"tinker"})          # must not raise
    c.require({"tinker", "anthropic"})
    with pytest.raises(ConsentError, match="does not name these provider"):
        c.require({"tinker", "openai"})


def test_consent_hash_ties_a_run_to_the_file_that_authorised_it(tmp_path):
    a = Consent.load(_consent_yaml(tmp_path))
    b = Consent.load(_consent_yaml(tmp_path, data_slice="something else"))
    assert a.sha256 != b.sha256
    assert len(a.sha256) == 64


def test_consent_config_omits_his_words_but_keeps_the_hash(tmp_path):
    """A run config gets copied into reports; the quote lives in the consent file and the plan."""
    cfg = Consent.load(_consent_yaml(tmp_path)).as_config()
    assert "consent_sha256" in cfg and "consent_providers" in cfg
    assert not any("upload" in str(v) for v in cfg.values())


# --- the prompt freeze ----------------------------------------------------------------------------

def test_dev_does_not_require_a_pinned_prompt():
    """Dev is where iteration is supposed to happen."""
    t = PromptTemplate.load(PROMPT_DIR / "prompt_b1.md")
    t.require_pinned(None, split="dev")  # must not raise


def test_test_split_requires_a_pinned_prompt():
    t = PromptTemplate.load(PROMPT_DIR / "prompt_b1.md")
    with pytest.raises(PromptFreezeError, match="requires --prompt-sha"):
        t.require_pinned(None, split="test")


def test_test_split_refuses_a_stale_pin():
    """The quietest way to turn a pre-registered comparison into a tuned one."""
    t = PromptTemplate.load(PROMPT_DIR / "prompt_b1.md")
    with pytest.raises(PromptFreezeError, match="does not match"):
        t.require_pinned(sha256_text("an older prompt"), split="test")


def test_test_split_accepts_the_matching_pin():
    t = PromptTemplate.load(PROMPT_DIR / "prompt_b1.md")
    t.require_pinned(t.sha256, split="test")  # must not raise


def test_missing_template_says_it_is_written_by_hand():
    with pytest.raises(FileNotFoundError, match="written by hand"):
        PromptTemplate.load(PROMPT_DIR / "prompt_does_not_exist.md")


# --- prompt rendering -----------------------------------------------------------------------------

def test_vocabulary_is_sorted_so_the_prompt_is_deterministic():
    assert render_vocabulary({"b", "a"}) == "- a\n- b"


def test_conversation_stops_at_the_target_turn():
    items = [
        item(2, "c1", "first", "a", reply="r1", turn=1),
        item(3, "c1", "second", "a", reply="r2", turn=2),
        item(4, "c1", "third", "a", reply="r3", turn=3),
    ]
    rendered = render_conversation(items, items[1])
    assert "first" in rendered and "second" in rendered
    assert "third" not in rendered, "a later turn is in the future"
    assert "r2" not in rendered, "the reply to the message being labelled must not be shown"


def test_build_prompt_fills_every_placeholder():
    items = [item(2, "c1", "hello", "a", turn=1)]
    t = PromptTemplate.load(PROMPT_DIR / "prompt_b1.md")
    out = build_prompt(t, items=items, target=items[0], vocabulary={"a", "b"}, fewshot=None)
    assert "{{" not in out
    assert "hello" in out and "- a" in out


def test_fewshot_block_is_empty_when_there_is_none():
    items = [item(2, "c1", "hello", "a", turn=1)]
    t = PromptTemplate.load(PROMPT_DIR / "prompt_b1.md")
    assert "Example 1" not in build_prompt(
        t, items=items, target=items[0], vocabulary={"a"}, fewshot=None
    )


# --- few-shot selection ---------------------------------------------------------------------------

def _train(n_per_class: int = 5) -> list[Item]:
    out: list[Item] = []
    row = 2
    for cls in ("a", "b", "c"):
        for i in range(n_per_class):
            out.append(item(row, f"conv-{row}", f"message {cls} {i}", cls, turn=1))
            row += 1
    return out


def test_fewshot_covers_every_class_before_filling_up():
    """A rare class represented, rather than crowded out by the majority."""
    chosen = select_fewshot(_train(), k=3, seed=0)
    assert {c.action for c in chosen} == {"a", "b", "c"}


def test_fewshot_returns_k_items():
    assert len(select_fewshot(_train(), k=FEWSHOT_K, seed=0)) == FEWSHOT_K


def test_fewshot_is_deterministic_under_a_seed():
    a = [i.item_id for i in select_fewshot(_train(), k=FEWSHOT_K, seed=3)]
    b = [i.item_id for i in select_fewshot(_train(), k=FEWSHOT_K, seed=3)]
    assert a == b


def test_fewshot_order_changes_with_the_seed():
    """Both the choice and the order move the result, which is why both go in the config."""
    a = [i.item_id for i in select_fewshot(_train(), k=FEWSHOT_K, seed=1)]
    b = [i.item_id for i in select_fewshot(_train(), k=FEWSHOT_K, seed=2)]
    assert a != b


def test_fewshot_refuses_an_unlabelled_train_split():
    with pytest.raises(ValueError, match="no labelled training items"):
        select_fewshot([item(2, "c", "m", "")], k=4, seed=0)


# --- answer extraction ----------------------------------------------------------------------------

VOCAB = {"ask_budget", "schedule_visit"}


def test_extracts_a_bare_label():
    assert extract_action("ask_budget", VOCAB) == "ask_budget"


def test_extracts_from_structured_output():
    assert extract_action('{"action": "schedule_visit"}', VOCAB) == "schedule_visit"


def test_extracts_from_an_action_prefix():
    assert extract_action("action: ask_budget", VOCAB) == "ask_budget"


def test_an_out_of_vocabulary_answer_is_returned_as_is():
    """Pre-registered: it counts as incorrect AND as a parse failure, so it must not be coerced."""
    assert extract_action("probably ask about the budget", VOCAB) == "probably ask about the budget"


def test_malformed_json_is_not_silently_accepted():
    assert extract_action('{"action": ', VOCAB) == '{"action":'


def test_extraction_is_strict_about_the_label_and_lenient_about_the_wrapper():
    assert extract_action("Sure!\naction: schedule_visit\n", VOCAB) == "schedule_visit"
    assert extract_action("ask budget", VOCAB) == "ask budget", "separators are not normalised away"


# --- the provider table ---------------------------------------------------------------------------

def _providers_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "providers.yaml"
    p.write_text(body, encoding="utf-8")
    return p


MINIMAL = """
price_table_version: "test"
rungs:
  B1: {provider_ref: p}
providers:
  p:
    backend: openai_compatible
    provider: tinker
    model: m
    price_per_mtok: {input: 1.0, output: 2.0}
"""


def test_providers_loads_and_reports_what_it_would_reach(tmp_path):
    p = Providers.load(_providers_yaml(tmp_path, MINIMAL))
    assert p.providers_reached(["B1"]) == {"tinker"}
    assert p.price_table_version == "test"


def test_price_table_version_is_required(tmp_path):
    body = MINIMAL.replace('price_table_version: "test"\n', "")
    with pytest.raises(ValueError, match="price_table_version is required"):
        Providers.load(_providers_yaml(tmp_path, body))


def test_unknown_rung_is_refused(tmp_path):
    body = MINIMAL.replace("B1:", "B9:")
    with pytest.raises(ValueError, match="unknown rung"):
        Providers.load(_providers_yaml(tmp_path, body))


def test_rung_pointing_at_a_missing_provider_is_refused(tmp_path):
    body = MINIMAL.replace("{provider_ref: p}", "{provider_ref: nope}")
    with pytest.raises(ValueError, match="unknown provider"):
        Providers.load(_providers_yaml(tmp_path, body))


def test_provider_needs_prices(tmp_path):
    body = MINIMAL.replace("    price_per_mtok: {input: 1.0, output: 2.0}\n", "")
    with pytest.raises(ValueError, match="missing 'price_per_mtok'"):
        Providers.load(_providers_yaml(tmp_path, body))


def test_cost_is_computed_per_million_tokens(tmp_path):
    p = Providers.load(_providers_yaml(tmp_path, MINIMAL))
    entry = p.entries["p"]
    assert entry.cost(1_000_000, 0) == pytest.approx(1.0)
    assert entry.cost(0, 1_000_000) == pytest.approx(2.0)


def test_unknown_backend_is_refused(tmp_path):
    body = MINIMAL.replace("backend: openai_compatible", "backend: telepathy")
    with pytest.raises(ValueError, match="unknown backend"):
        Providers.load(_providers_yaml(tmp_path, body)).entries["p"].build("B1")


def test_the_shipped_example_providers_file_loads():
    example = Path(__file__).resolve().parents[1] / "providers.example.yaml"
    p = Providers.load(example)
    assert set(p.by_rung) == set(MODEL_RUNGS)


# --- the stub backend -----------------------------------------------------------------------------

def test_stub_is_deterministic_and_offline():
    s = StubBackend(answers={"budget": "ask_budget"}, fallback="no_op")
    assert s.complete("what is the budget", constrain_to=None).text == "ask_budget"
    assert s.complete("something else", constrain_to=None).text == "no_op"
    assert len(s.calls) == 2


def test_stub_respects_a_constraint():
    """A constrained backend cannot emit an out-of-vocabulary answer, so the stub does not either."""
    s = StubBackend(fallback="not_in_vocab")
    out = s.complete("x", constrain_to=["a", "b"])
    assert out.text == "a"


def test_completion_records_what_was_sent():
    out = StubBackend().complete("x", constrain_to=None)
    assert isinstance(out, Completion)
    assert out.settings_sent["backend"] == "stub"


# --- Gate 2 ---------------------------------------------------------------------------------------

def _preds(correct: list[bool]):
    from baselines import Prediction

    return [
        Prediction(f"i{n}", f"c{n // 3}", "a", "a" if ok else "b")
        for n, ok in enumerate(correct)
    ]


def test_condition_1_passes_on_a_large_paired_gain():
    floor = _preds([False] * 100)
    best = _preds([True] * 60 + [False] * 40)
    g = gate_two(
        rung_scores={"B1": {"accuracy": 0.6}},
        prompted_rungs=["B1"],
        floor_name="B-triv-lex",
        floor_preds=floor,
        best_prompted="B1",
        best_preds=best,
        ceiling=None,
    )
    c = g["conditions"]["1_task_needs_a_language_model"]
    assert c["verdict"] == "PASS"
    assert c["difference_pp"] >= MIN_EFFECT_PP


def test_condition_1_fails_when_the_gain_is_below_the_threshold():
    """The honest outcome: the pattern is lexical and the track ends rather than reaching PE-003."""
    floor = _preds([True] * 55 + [False] * 45)
    best = _preds([True] * 60 + [False] * 40)
    g = gate_two(
        rung_scores={"B1": {"accuracy": 0.6}},
        prompted_rungs=["B1"],
        floor_name="B-triv-lex",
        floor_preds=floor,
        best_prompted="B1",
        best_preds=best,
        ceiling=None,
    )
    assert g["conditions"]["1_task_needs_a_language_model"]["verdict"] == "FAIL"
    assert g["overall"] == "FAIL"


def test_condition_2_is_not_established_without_a_ceiling():
    g = gate_two(
        rung_scores={"B1": {"accuracy": 0.6}},
        prompted_rungs=["B1"],
        floor_name="B-triv-maj",
        floor_preds=_preds([False] * 10),
        best_prompted="B1",
        best_preds=_preds([True] * 10),
        ceiling=None,
    )
    c = g["conditions"]["2_headroom_for_a_fine_tune"]
    assert c["verdict"] == "NOT_ESTABLISHED"
    assert c["reason"] == "no_label_noise_ceiling"


def test_condition_2_passes_when_there_is_headroom():
    g = gate_two(
        rung_scores={"B1": {"accuracy": 0.70}},
        prompted_rungs=["B1"],
        floor_name="B-triv-maj",
        floor_preds=_preds([False] * 10),
        best_prompted="B1",
        best_preds=_preds([True] * 10),
        ceiling=0.90,
    )
    c = g["conditions"]["2_headroom_for_a_fine_tune"]
    assert c["verdict"] == "PASS"
    assert c["headroom_pp"] == pytest.approx(20.0)


def test_condition_2_fails_when_the_prompted_rung_is_at_the_ceiling():
    """No headroom means no fine-tune to justify; the claim becomes cost, latency and on-prem."""
    g = gate_two(
        rung_scores={"B1": {"accuracy": 0.86}},
        prompted_rungs=["B1"],
        floor_name="B-triv-maj",
        floor_preds=_preds([False] * 10),
        best_prompted="B1",
        best_preds=_preds([True] * 10),
        ceiling=0.90,
    )
    assert g["conditions"]["2_headroom_for_a_fine_tune"]["verdict"] == "FAIL"


def test_frontier_rungs_do_not_count_toward_headroom():
    """Condition 2 is about the SMALL model's headroom; B4 sitting high is not the same thing."""
    g = gate_two(
        rung_scores={"B1": {"accuracy": 0.70}, "B4": {"accuracy": 0.89}},
        prompted_rungs=["B1"],
        floor_name="B-triv-maj",
        floor_preds=_preds([False] * 10),
        best_prompted="B1",
        best_preds=_preds([True] * 10),
        ceiling=0.90,
    )
    assert g["conditions"]["2_headroom_for_a_fine_tune"]["verdict"] == "PASS"


def test_gate_2_output_passes_the_guard():
    g = gate_two(
        rung_scores={"B1": {"accuracy": 0.6}},
        prompted_rungs=["B1"],
        floor_name="B-triv-lex",
        floor_preds=_preds([False] * 10),
        best_prompted="B1",
        best_preds=_preds([True] * 10),
        ceiling=0.9,
    )
    assert_output_safe(g, "$gate_2")


# --- the ladder -----------------------------------------------------------------------------------

def test_every_rung_is_defined():
    assert set(LADDER) == set(MODEL_RUNGS)


def test_only_b2_is_constrained_and_only_b3_has_examples():
    assert [r for r, v in LADDER.items() if v.constrained] == ["B2"]
    assert [r for r, v in LADDER.items() if v.fewshot] == ["B3"]


def test_b0_uses_its_own_prompt_and_the_rest_share_one():
    assert LADDER["B0"].prompt_file != LADDER["B1"].prompt_file
    assert len({LADDER[r].prompt_file for r in ("B1", "B2", "B3", "B4", "B5")}) == 1


# --- the B2 constraint check ----------------------------------------------------------------------
# B2 is B1 plus a constraint. An OpenAI-COMPATIBLE endpoint may accept `response_format` and ignore
# it, in which case B2 is B1 under another name and no other number here would show it.

from run_stage2 import _b2_constraint_check  # noqa: E402


def test_b2_check_fails_when_the_constrained_rung_has_parse_failures():
    """A constrained rung cannot emit an out-of-vocabulary answer. If it did, it was not constrained."""
    out = _b2_constraint_check({"B1": {"parse_failures": 7}, "B2": {"parse_failures": 3}})
    assert out["verdict"] == "FAIL"


def test_b2_check_passes_when_b2_is_clean_and_b1_is_not():
    out = _b2_constraint_check({"B1": {"parse_failures": 7}, "B2": {"parse_failures": 0}})
    assert out["verdict"] == "PASS"


def test_b2_check_is_not_established_when_both_are_clean():
    """Consistent with the constraint working and with B1 never needing it. Not evidence."""
    out = _b2_constraint_check({"B1": {"parse_failures": 0}, "B2": {"parse_failures": 0}})
    assert out["verdict"] == "NOT_ESTABLISHED"


def test_b2_check_without_b2():
    assert _b2_constraint_check({"B1": {"parse_failures": 0}})["verdict"] == "NOT_ESTABLISHED"
