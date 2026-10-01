---
paths:
  - "data/**"
  - "src/statelm/data/**"
  - "experiments/**/data*.py"
  - "experiments/**/*split*.py"
  - "experiments/**/*synth*.py"
---

# Data and split rules

- `data/splits/test/` is frozen once created. Never regenerate, filter, or "clean" it.
- Never read test labels during development, prompt design, or debugging. Evaluation scripts
  may read them; you may see only aggregate metrics.
- Never generate synthetic training data from test schemas, test field names, or test domains.
- Splits are assigned by **schema and domain**, not by random conversation, so that "unseen
  schema" actually means unseen. Record which split each schema belongs to in
  `data/splits/schema_assignment.json`.
- Every record carries provenance: `source` (human | synthetic | public-dataset),
  `generator` (model name + version, if synthetic), `labeler` (human ID or "auto"),
  `created_at`, `split`.
- Model output never becomes a gold label without explicit human verification, recorded in
  the `labeler` field.
- Pilot items used in EXP-000 and EXP-001 must never enter the final test split.
- Before writing any split, compute and log a hash of each split file in the run config.
