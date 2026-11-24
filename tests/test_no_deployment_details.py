"""Repository files describe the code, never a real deployment.

Two checks:

- A generic one, always on: no private (RFC 1918) IPv4 address in any repository file. Examples use
  the documentation ranges (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) instead.
- A private one: the words that would identify a real deployment (hosts, names, domains, ranges)
  are read from the file named by PRIVATE_WORDS_FILE, kept outside the repository, one word per
  line, `#` starting a comment. The list never lives in the repository, and a hit is reported by
  the word's number in that list and the file:line, never by the word itself. Without the
  variable the check is skipped (run it with `just privacy-check`).

Both checks fold the text first (NFKC, then every Unicode digit to its ASCII digit), so a full-width
or other-script spelling of an address or a word is caught too.

The pinned Python image `just test` runs in has no git, so the scan walks the tree and skips what
.gitignore keeps out of the repository, and any other checkout nested inside this one, instead of
asking git for the tracked files.
"""

import fnmatch
import ipaddress
import os
import re
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENV_VAR = "PRIVATE_WORDS_FILE"

# Not versioned: git's own folder, the account data compose.yml mounts, and the .gitignore patterns
ALWAYS_SKIPPED = (".git", "signal-cli")

IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.]*\d)")
# RFC 1918 (10/8, 172.16/12, 192.168/16), built from numbers so that this file never matches its own lists
PRIVATE_NETWORKS = [
    ipaddress.IPv4Network(((first << 24) | (second << 16), prefix))
    for first, second, prefix in ((10, 0, 8), (172, 16, 12), (192, 168, 16))
]


def ignored_patterns() -> list[str]:
    """The .gitignore patterns (a trailing / dropped), plus the folders that are never repository text."""
    patterns = list(ALWAYS_SKIPPED)
    for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "!")):
            patterns.append(line.strip("/"))
    return patterns


def is_ignored(part: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(part, pattern) for pattern in patterns)


def repository_files() -> list[Path]:
    patterns = ignored_patterns()
    found = []
    for folder, dirs, files in os.walk(ROOT):
        here = Path(folder)
        # Prune ignored folders and nested checkouts (a folder holding its own .git)
        dirs[:] = sorted(d for d in dirs if not is_ignored(d, patterns) and not (here / d / ".git").exists())
        found.extend(here / name for name in sorted(files) if not is_ignored(name, patterns))
    return sorted(found)


def repository_lines():
    """Yield (relative path, line number, line) for every line of every repository text file."""
    files = repository_files()
    assert any(path.name == "app.py" for path in files), "the scan found no source file"
    for path in files:
        data = path.read_bytes()
        if b"\0" in data:
            continue  # binary file
        relative = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            yield relative, number, line


def read_words(path: Path) -> list[tuple[int, str]]:
    """The words of a list file as (line number, case-folded word): blank lines and # comments skipped."""
    words = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        word = line.split("#", 1)[0].strip()
        if word:
            words.append((number, fold(word).casefold()))
    return words


def fold(text: str) -> str:
    """NFKC, then every character with a digit value (any script) as its ASCII digit."""
    out = []
    for char in unicodedata.normalize("NFKC", text):
        value = None if char.isascii() else unicodedata.digit(char, None)
        out.append(char if value is None else str(value))
    return "".join(out)


def word_hits(words: list[tuple[int, str]], line: str) -> list[int]:
    """The list line numbers of the words found in a line, case-insensitively and after folding."""
    folded = fold(line).casefold()
    return [number for number, word in words if word in folded]


def private_addresses(line: str) -> list[str]:
    found = []
    for match in IPV4.finditer(fold(line)):
        try:
            address = ipaddress.IPv4Address(match.group(1))
        except ValueError:
            continue  # not an address, e.g. a version number or 192.0.2.300
        if any(address in net for net in PRIVATE_NETWORKS):
            found.append(match.group(1))
    return found


def test_repository_files_hold_no_private_address():
    found = [
        f"{path}:{number}: {address}"
        for path, number, line in repository_lines()
        for address in private_addresses(line)
    ]
    assert not found, "private addresses in repository files (use 192.0.2.x / 198.51.100.x):\n" + "\n".join(found)


def test_repository_files_hold_no_private_word():
    name = os.environ.get(ENV_VAR, "")
    if not name:
        pytest.skip(f"{ENV_VAR} is not set: point it at your own word list, kept outside the repository")
    path = Path(name)
    if not path.is_file():
        pytest.fail(f"{ENV_VAR} does not name a readable file")
    words = read_words(path)
    if not words:
        pytest.fail(f"{ENV_VAR} names a list with no word")
    found = [
        f"{file}:{number}: word on line {word} of the list"
        for file, number, line in repository_lines()
        for word in word_hits(words, line)
    ]
    if found:
        # pytest.fail, not assert: the assertion rewriter would print the words
        pytest.fail("private words in repository files:\n" + "\n".join(found), pytrace=False)


def test_the_scan_skips_what_the_repository_ignores():
    patterns = ignored_patterns()
    names = {path.relative_to(ROOT).as_posix() for path in repository_files()}
    assert {"app.py", ".gitignore", "README.md"} <= names
    assert not any(is_ignored(part, patterns) for name in names for part in name.split("/"))


def test_the_ignore_patterns_come_from_the_gitignore():
    patterns = ignored_patterns()
    assert {".git", ".env", "secrets", "__pycache__", "*.pyc"} <= set(patterns)
    assert is_ignored("module.pyc", patterns)
    assert not is_ignored("app.py", patterns)


def test_a_nested_checkout_is_not_scanned(tmp_path, monkeypatch):
    (tmp_path / ".gitignore").write_text("*.log\n", "utf-8")
    (tmp_path / "app.py").write_text("", "utf-8")
    (tmp_path / "run.log").write_text("", "utf-8")
    nested = tmp_path / "copy"
    nested.mkdir()
    (nested / ".git").write_text("gitdir: elsewhere\n", "utf-8")
    (nested / "app.py").write_text("", "utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    assert [path.relative_to(tmp_path).as_posix() for path in repository_files()] == [".gitignore", "app.py"]


@pytest.mark.parametrize(
    ("text", "folded"),
    [
        ("\uff11\uff10\uff0e1\uff0e2\uff0e3", "10" + ".1.2.3"),  # full-width digits and dots
        ("\u0661\u0660.1.2.3", "10" + ".1.2.3"),  # Arabic-Indic digits
        ("\u0967\u0966.1.2.3", "10" + ".1.2.3"),  # Devanagari digits
        ("\U0001d7cf\U0001d7ce.1.2.3", "10" + ".1.2.3"),  # mathematical bold digits
        ("Caf\u00e9 menu", "Caf\u00e9 menu"),  # accented letters stay
        ("x\u00b2", "x2"),  # NFKC turns a superscript into a digit
    ],
)
def test_fold_turns_every_digit_to_ascii(text, folded):
    assert fold(text) == folded


def test_a_private_address_in_other_digits_is_caught():
    # Full-width and Arabic-Indic spellings of a private address
    assert private_addresses("gateway \uff11\uff19\uff12.168.1.20")
    assert private_addresses("host \u0661\u0660.1.2.3")
    assert not private_addresses("doc \uff11\uff19\uff12.0.2.10")


def test_a_private_word_in_other_digits_or_width_is_caught():
    words = [(1, fold("unit42").casefold())]
    assert word_hits(words, "the \uff35\uff4e\uff49\uff54\uff14\uff12 room") == [1]
    assert word_hits(words, "unit\u0664\u0662") == [1]


def test_read_words_skips_comments_and_blank_lines(tmp_path):
    path = tmp_path / "words"
    path.write_text("# a comment\n\n  Alpha  \nbeta # trailing comment\n   # indented comment\nGamma Delta\n", "utf-8")
    assert read_words(path) == [(3, "alpha"), (4, "beta"), (6, "gamma delta")]


def test_word_hits_match_case_insensitively_and_give_the_list_line():
    words = [(3, "alpha"), (4, "beta"), (6, "gamma delta")]
    assert word_hits(words, "nothing here") == []
    assert word_hits(words, "the ALPHA host") == [3]
    assert word_hits(words, "AlphaBeta") == [3, 4]
    assert word_hits(words, "a Gamma Delta room") == [6]


def test_a_hit_never_prints_the_word(tmp_path, monkeypatch):
    words = tmp_path / "words"
    words.write_text("zz-secret-word\n", "utf-8")
    monkeypatch.setenv(ENV_VAR, str(words))
    monkeypatch.setattr(
        sys.modules[__name__],
        "repository_lines",
        lambda: iter([("README.md", 7, "see ZZ-Secret-Word here")]),
    )
    with pytest.raises(pytest.fail.Exception) as failure:
        test_repository_files_hold_no_private_word()
    message = str(failure.value)
    assert "README.md:7: word on line 1 of the list" in message
    assert "secret" not in message.casefold()


def test_without_the_variable_the_word_check_skips(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(pytest.skip.Exception, match=ENV_VAR):
        test_repository_files_hold_no_private_word()


def test_a_missing_or_empty_list_fails(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "missing"))
    with pytest.raises(pytest.fail.Exception, match="readable file"):
        test_repository_files_hold_no_private_word()
    empty = tmp_path / "empty"
    empty.write_text("# only a comment\n", "utf-8")
    monkeypatch.setenv(ENV_VAR, str(empty))
    with pytest.raises(pytest.fail.Exception, match="no word"):
        test_repository_files_hold_no_private_word()


@pytest.mark.parametrize(
    "line",
    [
        # Each address is split so that this file never matches its own examples
        "MOONIE_SIGNAL_WEBHOOK_URL=http://" + "10" + ".1.2.3:5678/hook",
        "gateway " + "172" + ".20.0.1",
        "ip: " + "192" + ".168.1.20",
    ],
)
def test_private_addresses_are_caught(line):
    assert private_addresses(line)


@pytest.mark.parametrize(
    "line",
    [
        "MOONIE_SIGNAL_WEBHOOK_URL=http://192.0.2.10:5678/hook",
        "ip: 198.51.100.20, client 203.0.113.9",
        "listen 127.0.0.1 and 0.0.0.0",
        "python:3.13.18-slim",
        "invalid ip 192.0.2.300",
        "multicast 224.0.0.1",
        "version 10.1.2",
    ],
)
def test_generic_addresses_are_allowed(line):
    assert not private_addresses(line)


def test_the_private_networks_are_rfc_1918():
    assert [(net.network_address.packed[:2], net.prefixlen) for net in PRIVATE_NETWORKS] == [
        (bytes([10, 0]), 8),
        (bytes([172, 16]), 12),
        (bytes([192, 168]), 16),
    ]
