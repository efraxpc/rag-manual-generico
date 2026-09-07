# Repository Guidelines

## Project Structure & Module Organization

Application code lives in `app/`. `app/main.py` builds the FastAPI application, `app/api/v1/endpoints/` contains versioned HTTP handlers, `app/schemas/` holds Pydantic request and response models, and `app/core/` contains configuration and shared exceptions. Mirror those boundaries when adding features rather than placing business logic in route handlers. Tests live in `tests/` and currently exercise the API through FastAPI's `TestClient`. Azure infrastructure is maintained separately in `infrastructure/terraform/`; its README documents resources and deployment assumptions.

## Build, Test, and Development Commands

Create an isolated development environment from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Run `uvicorn app.main:app --reload` for local development. Use `pytest` to run the test suite, `ruff check .` to lint imports and Python code, and `ruff format --check .` to verify formatting. Build the production image with `docker build -t rag-manual-api .`.

For infrastructure changes, run `terraform fmt -check`, `terraform validate`, and `terraform plan` from `infrastructure/terraform/`. Never apply a plan merely to verify a pull request.

## Coding Style & Naming Conventions

Target Python 3.11, use four-space indentation, type annotations, and an 88-character line limit. Ruff enforces `E`, `F`, `I`, `UP`, and `B` rules. Use `snake_case` for modules, functions, and variables; `PascalCase` for classes and Pydantic models; and descriptive endpoint modules such as `health.py`. Keep routes under `/api/v1` and obtain settings through `get_settings()` rather than reading environment variables throughout the application. Format Terraform with `terraform fmt`.

## Testing Guidelines

Name test files `test_*.py` and test functions `test_*`. Add tests for success responses, validation failures, and relevant error handling whenever an endpoint changes. Keep tests deterministic and independent of live Azure resources. No coverage threshold is configured; nevertheless, new behavior should be covered before review.

## Commit & Pull Request Guidelines

Recent history favors concise, scoped subjects such as `feat(terraform): ...`; use Conventional Commit prefixes (`feat`, `fix`, `test`, `docs`, `chore`) and an optional scope. Keep each commit focused. Pull requests should explain the change and verification commands, link related issues, and call out configuration or infrastructure impact. Include example requests/responses for API changes and a redacted `terraform plan` summary for Terraform changes; never attach secrets or state files.

## Security & Configuration

Copy `.env.example` locally and keep credentials out of Git. Do not commit `.env`, `terraform.tfvars`, plan files, or Terraform state. Prefer managed identities and least-privilege Azure RBAC, consistent with the existing infrastructure design.
