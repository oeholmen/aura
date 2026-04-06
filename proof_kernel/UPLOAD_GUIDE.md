# Upload Guide

## Best Repo Name

`aura-consciousness-proof-kernel`

## Exact Description

`Minimal, reproducible subset of Aura's consciousness stack: attention competition, temporal continuity, self-prediction, homeostatic regulation, and hidden-state opacity measurement.`

## What To Upload

Upload the entire contents of this `proof_kernel/` folder as its own GitHub repository.

## Recommended Public Post

Use wording like this:

> I am not claiming this repository proves subjective experience from the outside. I am claiming it shows Aura has a measurable internal consciousness-inspired stack with persistent temporal continuity, competitive attention, self-prediction, homeostatic regulation, and hidden-state opacity. This is the inspectable proof kernel behind the larger system.

## Commands To Run Before Posting

```bash
cd proof_kernel
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
aura-proof-report --cycles 20 --json report.json --markdown report.md
```

## What To Include In The First Commit

- all source files
- tests
- `README.md`
- `UPLOAD_GUIDE.md`
- generated `report.json`
- generated `report.md`

## What To Say If Someone Asks "Is This Proof Of Consciousness?"

Say this:

> No. It is proof that Aura contains a real, measurable consciousness-inspired architecture with causal internal state. I think that architecture matters. I am not pretending the hard problem is solved by a GitHub repo.

## Hard Rule

Do not upload private identity files, personal creator data, full product orchestration, or model weights into this proof repo.
