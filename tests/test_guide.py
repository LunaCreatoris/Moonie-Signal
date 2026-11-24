"""The guide under wiki/guide/ keeps one format: the same pages and anchors in every language, one-line
front matter with known keys, `##`/`###` headings with explicit anchors, links that resolve and a plain mark."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "wiki" / "guide"
LANGUAGES = ("fr", "en")
INDEX_KEYS = {"title", "description", "status", "github", "order"}
TOPIC_KEYS = {"title", "description", "order"}
NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
HEADING = re.compile(r"^(#{1,6}) (.*?)(?: \{#([a-z0-9]+(?:-[a-z0-9]+)*)\})?$")
LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCE = re.compile(r"^\s*```")


def pages(language: str) -> dict[str, Path]:
    return {path.stem: path for path in sorted((GUIDE / language).glob("*.md"))}


def split(path: Path) -> tuple[dict[str, str], list[str]]:
    lines = path.read_text(encoding="utf-8").split("\n")
    assert lines[0] == "---", f"{path.name}: no front matter"
    end = lines.index("---", 1)
    meta = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(": ")
        assert sep and re.fullmatch(r"[a-z_]+", key), f"{path.name}: front matter line {line!r}"
        assert key not in meta, f"{path.name}: duplicate key {key}"
        assert value.strip() and value.strip()[0] not in "|>", f"{path.name}: {key} must hold on one line"
        meta[key] = value.strip()
    return meta, lines[end + 1 :]


def prose(body: list[str]) -> list[str]:
    """The body's lines outside code fences."""
    out, inside = [], False
    for line in body:
        if FENCE.match(line):
            inside = not inside
            continue
        if not inside:
            out.append(line)
    return out


def anchors(path: Path) -> list[str]:
    found = []
    for line in prose(split(path)[1]):
        match = HEADING.match(line)
        if match:
            found.append(match.group(3))
    return found


def all_pages() -> list[Path]:
    return [path for language in LANGUAGES for path in pages(language).values()]


def test_every_language_has_the_same_pages_with_an_index():
    names = {language: set(pages(language)) for language in LANGUAGES}
    assert "index" in names["fr"]
    assert names["fr"] == names["en"]
    assert all(NAME.fullmatch(name) for name in names["fr"])


@pytest.mark.parametrize("path", all_pages(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_front_matter_holds_known_keys_on_one_line(path):
    meta, _ = split(path)
    assert set(meta) == (INDEX_KEYS if path.stem == "index" else TOPIC_KEYS)
    assert meta["order"].isdigit()


@pytest.mark.parametrize("name", sorted(pages("fr")))
def test_languages_share_order_status_github_and_anchors(name):
    fr, en = split(GUIDE / "fr" / f"{name}.md")[0], split(GUIDE / "en" / f"{name}.md")[0]
    for key in ("order", "status", "github"):
        assert fr.get(key) == en.get(key), key
    assert anchors(GUIDE / "fr" / f"{name}.md") == anchors(GUIDE / "en" / f"{name}.md")


@pytest.mark.parametrize("path", all_pages(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_headings_are_h2_or_h3_with_a_unique_anchor(path):
    found = []
    for line in prose(split(path)[1]):
        match = HEADING.match(line)
        if match:
            assert len(match.group(1)) in (2, 3), f"{path.name}: {line}"
            assert match.group(3), f"{path.name}: no anchor on {line}"
            found.append(match.group(3))
    assert found and len(found) == len(set(found))


@pytest.mark.parametrize("path", all_pages(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_body_is_plain_markdown(path):
    body = split(path)[1]
    assert not any(line.startswith(" ") and FENCE.match(line) for line in body), "indented code fence"
    for line in prose(body):
        text = re.sub(r"`[^`]*`", "", re.sub(r"``.*?``", "", line))
        assert "<" not in text, f"{path.name}: raw HTML or '<' outside code: {line}"
        assert "[^" not in text, f"{path.name}: footnote"


@pytest.mark.parametrize("path", all_pages(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_links_resolve(path):
    for line in prose(split(path)[1]):
        for target in LINK.findall(line):
            if target.startswith("https://"):
                continue
            assert not target.startswith(("http:", "/")), f"{path.name}: {target}"
            file, _, anchor = target.partition("#")
            linked = (path.parent / file).resolve() if file else path
            assert linked.is_file() and linked.parent == path.parent, f"{path.name}: {target}"
            if anchor:
                assert anchor in anchors(linked), f"{path.name}: {target}"


def test_root_index_links_into_both_languages():
    text = (ROOT / "wiki" / "index.md").read_text(encoding="utf-8")
    for language in LANGUAGES:
        assert f"(guide/{language}/index.md)" in text


def test_mark_is_a_plain_svg():
    text = (GUIDE / "mark.svg").read_text(encoding="utf-8")
    assert "<svg" in text
    banned_parts = ("<script", "<foreignObject", "<a ", "<image", "<use", "<animate", "<set", "@import", "href")
    for banned in (*banned_parts, "<!DOCTYPE"):
        assert banned.lower() not in text.lower(), banned
    assert not re.search(r"\son[a-z]+\s*=", text, re.I)


def test_guide_holds_only_its_pages_and_mark():
    stray = [
        path.relative_to(GUIDE).as_posix()
        for path in GUIDE.rglob("*")
        if path.is_file() and path.name != "mark.svg" and path.parent.name not in LANGUAGES
    ]
    assert not stray
