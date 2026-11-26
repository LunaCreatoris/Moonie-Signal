# Moonie Signal: every recipe runs in the pinned Python image, the same on macOS, Linux and Windows.

python_image := "python:3.13.18-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90"
image := "moonie-signal:local"
in_python := "docker run --rm -v " + quote(justfile_directory()) + ":/src -w /src -e PIP_ROOT_USER_ACTION=ignore -e PIP_DISABLE_PIP_VERSION_CHECK=1 " + python_image + " sh -c"

# List the recipes
default:
    @just --list

# Run the tests
test:
    {{in_python}} "pip install -q -r requirements-dev.txt && pytest"

# Scan the repository files for your private words (PRIVATE_WORDS_FILE: your own list, kept outside the repo)
privacy-check:
    {{ if env_var_or_default("PRIVATE_WORDS_FILE", "") == "" { error("set PRIVATE_WORDS_FILE to your word list, kept outside the repository") } else { "" } }}docker run --rm -v {{quote(justfile_directory())}}:/src -v {{quote(join(invocation_directory(), env_var_or_default("PRIVATE_WORDS_FILE", "")))}}:/run/private-words:ro -e PRIVATE_WORDS_FILE=/run/private-words -e PIP_ROOT_USER_ACTION=ignore -e PIP_DISABLE_PIP_VERSION_CHECK=1 -w /src {{python_image}} sh -c "pip install -q -r requirements-dev.txt && pytest -rs tests/test_no_deployment_details.py"

# Lint and check the formatting
lint:
    {{in_python}} "pip install -q -r requirements-dev.txt && ruff check . && ruff format --check ."

# Format the code
format:
    {{in_python}} "pip install -q -r requirements-dev.txt && ruff format . && ruff check --fix ."

# The merge gate, and the only CI: lint, then every test
ci: lint test

# Build the image
build:
    docker build -t {{image}} .

# Run the stack from compose.yml with .env (compose builds the image from this checkout)
run:
    docker compose up -d

# Follow the relay's log
logs:
    docker compose logs -f moonie

# Stop the stack
stop:
    docker compose down

# Re-pin requirements*.txt to the latest versions (needs uv on the host)
lock:
    uv pip compile --quiet --python-version 3.13 --no-annotate --no-header --upgrade requirements.in -o requirements.txt
    uv pip compile --quiet --python-version 3.13 --no-annotate --no-header --upgrade requirements-dev.in -o requirements-dev.txt
