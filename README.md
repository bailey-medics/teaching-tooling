# teaching-tooling

Shared validation and deployment tooling for teaching content repositories.

## Overview

This repo provides:

- **Validation scripts** — ensure module metadata and MDX content are correct before merge
- **Reusable GitHub Actions workflows** — organisation repos call these as thin workflow callers

Organisation repos (e.g. `eoeeta-teaching`, `respiratory-teaching`) contain only content — no scripts. All tooling is centralised here.

## Structure

```
scripts/
├── validate.py          # Module metadata + assessment validation (Pydantic)
└── validate_mdx.js      # MDX parse + validate (CI gate)

tests/
├── fixtures/            # Golden test modules (valid + invalid)
├── test_validate.py     # pytest for validate.py
└── test_mdx.js          # Node.js tests for MDX scripts

.github/workflows/
├── validate.yml         # Reusable workflow: PR validation gate
├── deploy.yml           # Reusable workflow: build + deploy to GCS/API
└── self-test.yml        # CI for teaching-tooling itself
```

## Usage from organisation repos

### Validate on PR

```yaml
# .github/workflows/validate.yml
on:
  pull_request:
jobs:
  validate:
    uses: bailey-medics/teaching-tooling/.github/workflows/validate.yml@main
    with:
      org_id: eoeeta
    secrets: inherit
```

### Deploy on push to main

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]
jobs:
  deploy:
    uses: bailey-medics/teaching-tooling/.github/workflows/deploy.yml@main
    with:
      org_id: eoeeta
    secrets: inherit
```

## Local development

### Python (metadata validation)

```bash
pip install -r requirements.txt
python scripts/validate.py /path/to/modules/
```

### Node.js (MDX validation)

```bash
npm install
node scripts/validate_mdx.js /path/to/modules/
```

### Running tests

```bash
# Python
pip install -r requirements-dev.txt
pytest tests/

# Node.js
npm test
```

## Version pinning

Organisation repos reference a tag (e.g. `@v1`) for stability. Use `@main` during initial development, then switch to tags before adding additional organisations.

## Adding a new organisation

1. Create a new private repo (use `respiratory-teaching` as a template)
2. Add `modules/` with at least one module containing `module.yaml`
3. Add `.github/workflows/validate.yml` and `deploy.yml` (thin callers)
4. Configure secrets: `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `GCP_TEACHING_GCS_BUCKET`, `BACKEND_SYNC_URL`, `BACKEND_SYNC_TOKEN`

## Content format

See the [learning section plan](https://github.com/bailey-medics/quillmedical/blob/main/docs/docs/plans/learning-section-plan.md) for the full MDX content format specification.
