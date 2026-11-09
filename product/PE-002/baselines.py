"""Stage 1: the two trivial baselines, B-triv-maj and B-triv-lex.

Both are fitted on **train only** and scored on dev and test, like any other rung. Neither calls a
model, touches the network, or spends a credit.

Why these two are the first thing PE-002 runs, from the record: if a linear model on word counts
matches what the prompted models do, the pattern is lexical, an SLM is not needed, and no amount of
fine-tuning is the right answer. That finding costs nothing and arrives before any client text
leaves the machine.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from data import Item
from scoring import Scored


@dataclass(frozen=True)
class Prediction:
    item_id: str
    conversation_id: str
    gold: str
    predicted: str

    @property
    def correct(self) -> bool:
        # Exact match after the case and whitespace normalisation the record pre-registers, and
        # nothing else. Mapping a near miss onto the nearest class would be scoring generously.
        return _norm(self.predicted) == _norm(self.gold)


def _norm(label: str) -> str:
    return " ".join((label or "").split()).casefold()


def to_scored(preds: list[Prediction]) -> list[Scored]:
    return [Scored(p.item_id, p.conversation_id, p.correct) for p in preds]


# --- B-triv-maj -----------------------------------------------------------------------------------

def fit_majority(train: list[Item]) -> str:
    """The most frequent `action` in train. Ties break on the label, so the fit is deterministic."""
    counts = Counter(_norm(i.action) for i in train if i.action.strip())
    if not counts:
        raise ValueError("no labelled training items: cannot fit a majority baseline")
    best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return best[0]


def predict_majority(label: str, items: list[Item]) -> list[Prediction]:
    return [
        Prediction(i.item_id, i.conversation_id, i.action, label)
        for i in items
        if i.action.strip()
    ]


# --- B-triv-lex -----------------------------------------------------------------------------------

def fit_predict_lexical(
    train: list[Item], evaluate: list[Item], *, seed: int
) -> tuple[list[Prediction], dict[str, object]]:
    """TF-IDF over the user message, then multinomial logistic regression.

    Imported lazily so that B-triv-maj, the split writer and every test that does not need
    scikit-learn can run without it installed.

    Settings are fixed here rather than tuned: tuning a baseline on dev and then reporting it as
    "the trivial baseline" would overstate the floor, and the floor is the thing Gate 2 condition 1
    compares against. Word unigrams and bigrams, sublinear term frequency, no feature cap, L2
    regularisation at the library default, and a fixed seed.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    train_l = [i for i in train if i.action.strip()]
    eval_l = [i for i in evaluate if i.action.strip()]
    if not train_l:
        raise ValueError("no labelled training items: cannot fit the lexical baseline")

    y = [_norm(i.action) for i in train_l]
    if len(set(y)) < 2:
        # One class in train makes logistic regression degenerate, and it would then be the
        # majority baseline wearing a different name. Say so rather than report it as a second
        # independent baseline.
        raise ValueError(
            "train has a single `action` class, so the lexical baseline is identical to the "
            "majority baseline. Report B-triv-maj alone and record why."
        )

    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True)
    x_train = vec.fit_transform(i.user_message for i in train_l)
    clf = LogisticRegression(max_iter=2000, random_state=seed)
    clf.fit(x_train, y)

    x_eval = vec.transform(i.user_message for i in eval_l)
    predicted = clf.predict(x_eval)
    preds = [
        Prediction(i.item_id, i.conversation_id, i.action, str(p))
        for i, p in zip(eval_l, predicted)
    ]
    settings = {
        "ngram_range": [1, 2],
        "sublinear_tf": True,
        "max_iter": 2000,
        "random_state": seed,
        "n_features": int(x_train.shape[1]),
        "n_train_items": len(train_l),
        "n_classes_in_train": len(set(y)),
    }
    return preds, settings


# --- shared ---------------------------------------------------------------------------------------

def parse_failures(preds: list[Prediction], vocabulary: set[str]) -> int:
    """Predictions outside the action vocabulary.

    Always 0 for both stage-1 baselines, by construction: each can only emit a class it saw in
    train. Computed and reported anyway, because stage 2's model rungs can emit anything and the
    record pre-registers that such an output counts as incorrect *and* is counted here. A column
    that is structurally 0 in stage 1 and non-zero in stage 2 is the point.
    """
    return sum(1 for p in preds if _norm(p.predicted) not in vocabulary)


def vocabulary_of(items: list[Item]) -> set[str]:
    return {_norm(i.action) for i in items if i.action.strip()}
