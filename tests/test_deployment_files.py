"""The files a reader deploys with (compose.yml, .env.example, Dockerfile, justfile, README) agree with each other."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.yml").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
JUSTFILE = (ROOT / "justfile").read_text(encoding="utf-8")
GITIGNORE = (ROOT / ".gitignore").read_text(encoding="utf-8")
GUIDE = ROOT / "wiki" / "guide"

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
    # No image is published: every `up`, a Portainer redeploy included, builds the checkout's code
    assert re.search(r"^    pull_policy: build$", service, re.MULTILINE)
    assert re.search(r"^    image: \$\{MOONIE_SIGNAL_IMAGE:-[^}]+\}$", service, re.MULTILINE)


# ${NAME}, ${NAME:-default} or ${NAME:?message}, as Compose interpolates them
VARIABLE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::([-?])([^}]*))?\}")
REQUIRED = {"MOONIE_SIGNAL_ACCOUNT", "MOONIE_SIGNAL_WEBHOOK_URL"}


def interpolate(text: str, env: dict[str, str]) -> str:
    """Compose's interpolation: an empty value counts as unset for `:-` and `:?`."""

    def value(match: re.Match) -> str:
        name, kind, rest = match.groups()
        if env.get(name):
            return env[name]
        if kind == "?":
            raise KeyError(f"{name}: {rest}")
        assert kind == "-", f"{name} has no default: plain docker compose would warn and use an empty value"
        return rest

    return VARIABLE.sub(value, text)


def compose_lines() -> str:
    return "\n".join(line for line in COMPOSE.splitlines() if not line.lstrip().startswith("#"))


def test_compose_runs_with_only_the_required_settings_and_no_just():
    # Plain `docker compose up` or a Portainer stack: nothing but the two required values is set
    rendered = interpolate(compose_lines(), {name: "x" for name in REQUIRED})
    assert "${" not in rendered
    assert "- ./signal-cli:/home/.local/share/signal-cli" in rendered
    assert "file: ./secrets/push_token" in rendered
    for name in sorted(REQUIRED):
        try:
            interpolate(compose_lines(), {other: "x" for other in REQUIRED - {name}})
        except KeyError as error:
            assert name in str(error)
        else:
            raise AssertionError(f"{name} is not required by compose.yml")


def test_the_host_folders_take_absolute_paths():
    # Portainer CE resolves no relative bind mount of a Git stack: the folders must be movable
    env = {name: "x" for name in REQUIRED}
    env |= {"MOONIE_SIGNAL_DATA_DIR": "/srv/moonie-signal/signal-cli", "MOONIE_SIGNAL_SECRETS_DIR": "/srv/s"}
    rendered = interpolate(compose_lines(), env)
    assert "- /srv/moonie-signal/signal-cli:/home/.local/share/signal-cli" in rendered
    assert "file: /srv/s/push_token" in rendered


def test_every_compose_variable_is_in_the_example():
    used = {match.group(1) for match in VARIABLE.finditer(compose_lines())} - {"TZ"}
    listed = set(re.findall(r"^(MOONIE_[A-Z_]+)=", ENV_EXAMPLE, re.MULTILINE))
    assert used <= listed, sorted(used - listed)


def test_the_justfile_sets_no_compose_variable():
    # The just path and the plain compose path must run the same stack
    assert "MOONIE_" not in JUSTFILE


def test_git_keeps_the_local_state_out():
    lines = set(GITIGNORE.splitlines())
    assert {".env", "secrets/", "signal-cli/"} <= lines


def test_the_guide_names_the_pinned_signal_cli_version():
    pinned = re.search(r"image: bbernhard/signal-cli-rest-api:([^@\s]+)@", COMPOSE).group(1)
    for page in sorted(GUIDE.glob("*/*.md")):
        for tag in re.findall(r"bbernhard/signal-cli-rest-api:([^@\s`]+)", page.read_text(encoding="utf-8")):
            assert tag == pinned, f"{page.parent.name}/{page.name} names {tag}, compose.yml pins {pinned}"


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
