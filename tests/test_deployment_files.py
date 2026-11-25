"""The files a reader deploys with (compose.yml, .env.example, Dockerfile, justfile, README) agree with each other."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.yml").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
JUSTFILE = (ROOT / "justfile").read_text(encoding="utf-8")

# Fixed by compose.yml itself: the API is the `signal` service, the port is the one push clients call
SET_BY_COMPOSE = {"MOONIE_SIGNAL_API_URL", "MOONIE_HTTP_PORT"}


def readme_settings() -> set[str]:
    return set(re.findall(r"^\| `(MOONIE_[A-Z_]+)` \|", README, re.MULTILINE))


def compose_environment() -> dict[str, str]:
    """The `moonie` service's environment entries, as name -> value text."""
    service = COMPOSE.split("\n  moonie:\n", 1)[1].split("\n  signal:\n", 1)[0]
    return dict(re.findall(r"^      (MOONIE_[A-Z_]+): (.*)$", service, re.MULTILINE))


def test_the_readme_documents_settings():
    assert {
        "MOONIE_SIGNAL_ACCOUNT",
        "MOONIE_SIGNAL_WEBHOOK_TOKEN_FILE",
        "MOONIE_HTTP_MAX_BODY_BYTES",
    } <= readme_settings()


def test_compose_passes_every_documented_setting_from_env():
    environment = compose_environment()
    for name in sorted(readme_settings() - SET_BY_COMPOSE - {"MOONIE_SIGNAL_PUSH_TOKEN_FILE"}):
        assert name in environment, f"{name} is documented but compose.yml does not pass it"
        assert environment[name].startswith("${" + name + ":"), f"{name} is not read from .env"


def test_compose_builds_the_image_from_the_checkout():
    service = COMPOSE.split("\n  moonie:\n", 1)[1].split("\n  signal:\n", 1)[0]
    assert re.search(r"^    build: \.$", service, re.MULTILINE)


def test_the_required_settings_are_empty_in_the_example():
    # A filled-in placeholder would slip past compose's `:?` guard
    for name in ("MOONIE_SIGNAL_ACCOUNT", "MOONIE_SIGNAL_WEBHOOK_URL"):
        assert re.search(rf"^{name}=$", ENV_EXAMPLE, re.MULTILINE), f"{name} must be empty in .env.example"
        assert re.search(rf"^      {name}: \$\{{{name}:\?", COMPOSE, re.MULTILINE)


def test_the_health_check_follows_the_configured_port():
    healthcheck = DOCKERFILE.split("HEALTHCHECK", 1)[1].split("\nCMD", 1)[0]
    assert "MOONIE_HTTP_PORT" in healthcheck


def test_the_justfile_quotes_the_checkout_path():
    # A checkout path with spaces must not split the docker command
    assert JUSTFILE.count("justfile_directory()") == JUSTFILE.count("quote(justfile_directory())")


def test_the_privacy_check_explains_a_missing_word_list():
    assert 'env_var("PRIVATE_WORDS_FILE")' not in JUSTFILE
    assert 'env_var_or_default("PRIVATE_WORDS_FILE"' in JUSTFILE


def test_the_readme_links_the_guide_in_both_languages():
    assert "(wiki/guide/en/index.md)" in README
    assert "(wiki/guide/fr/index.md)" in README
