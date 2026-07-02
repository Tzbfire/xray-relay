# Repository Guidelines

## Project Structure & Module Organization
This repository builds a single-container Xray/sing-box relay admin service. The Python backend lives in `single/relay_admin/`, with `single/app.py` as the runtime entry point and `single/entrypoint.sh` preparing bundled core binaries. Static admin UI assets are in `single/relay_admin/static/` (`index.html`, `app.js`, `app.css`). Docker orchestration is defined by the root `docker-compose.yml`; `single/Dockerfile` builds the production image. Tests are in `tests/`, while extra protocol experiments live under `protocol-lab/`. Runtime state and downloaded binaries are stored in `data/` and `bin/` and should not be committed.

## Build, Test, and Development Commands
- `docker compose up -d --build`: build the image and start the relay container.
- `docker compose ps`: check container status and port mappings.
- `docker logs -f xray-singbox-relay`: follow backend and core process logs.
- `python -m pytest tests`: run the test suite with pytest when available.
- `python -m unittest discover -s tests`: stdlib fallback for the current unittest-style tests.

## Coding Style & Naming Conventions
Use Python 3.12-compatible code and standard library dependencies unless a new dependency is clearly justified. Follow PEP 8 conventions: 4-space indentation, `snake_case` functions and variables, and descriptive module names. Keep JSON keys and API payload fields stable because the static frontend calls `/api/*` endpoints directly. For frontend changes, keep vanilla JavaScript/CSS in `single/relay_admin/static/` and prefer small, focused functions.

## Testing Guidelines
Add or update tests in `tests/test_*.py` for parser, config builder, node, and service changes. Name test classes and methods descriptively, for example `ShareLinkTests.test_parse_anytls_link`. Prefer deterministic unit tests that do not require live proxy servers or external network access. Run the full test command before submitting changes.

## Commit & Pull Request Guidelines
Recent history uses short imperative subjects, often Conventional Commit prefixes such as `feat:`, `fix:`, and `docs:`. Keep commits focused and mention user-visible behavior or configuration impact. Pull requests should include a concise summary, test results, affected ports/env vars if relevant, and screenshots or notes for admin UI changes.

## Security & Configuration Tips
Copy `.env.example` to `.env` for local overrides. Do not commit `data/nodes.json`, generated configs, `bin/`, private share links, or credentials. Prefer pinned image digests for reproducible deployments; test tag upgrades before using them in production-like instances.
