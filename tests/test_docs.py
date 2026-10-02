"""Docs stay in sync with the CLI: every command is covered by the agent skill
and the JSON reference, the skill is valid, and both languages track releases."""

import argparse
import re
from pathlib import Path

from finresearch import cli

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "finresearch" / "SKILL.md"


def _leaf_commands():
    parser, _ = cli.build_parser()

    def walk(p, prefix=()):
        subs = [a for a in p._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            yield " ".join(prefix)
            return
        for name, sp in subs[0].choices.items():
            yield from walk(sp, prefix + (name,))
    return list(walk(parser))


def test_every_command_is_in_the_skill_and_json_reference():
    skill = SKILL.read_text(encoding="utf-8")
    ref = (ROOT / "docs" / "JSON.md").read_text(encoding="utf-8")
    missing = [(cmd, doc) for cmd in _leaf_commands()
               for doc, text in (("SKILL.md", skill), ("docs/JSON.md", ref))
               if not re.search(rf"(?<![\w-]){re.escape(cmd)}(?![\w-])", text)]
    assert missing == []


def test_skill_frontmatter_and_reference_link():
    text = SKILL.read_text(encoding="utf-8")
    m = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", text)
    assert m, "SKILL.md must open with name/description YAML frontmatter"
    name, description = m.group(1).strip(), m.group(2).strip()
    assert name == SKILL.parent.name and re.fullmatch(r"[a-z0-9-]{1,64}", name)
    assert 0 < len(description) <= 1024
    assert (SKILL.parent / "references" / "JSON.md").resolve() == (ROOT / "docs" / "JSON.md")


def test_japanese_docs_track_every_release():
    versions = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", (ROOT / "CHANGELOG.md").read_text(), re.M)
    ja = (ROOT / "CHANGELOG.ja.md").read_text(encoding="utf-8")
    assert versions and all(f"## [{v}]" in ja for v in versions)
    assert "README.md" in (ROOT / "README.ja.md").read_text(encoding="utf-8")
    assert "README.ja.md" in (ROOT / "README.md").read_text(encoding="utf-8")
