"""Every source file must be valid UTF-8 with no mojibake markers."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent / "precutter"
MOJIBAKE_RE = re.compile(r"Ã.|Å.")


def _sources():
    return [p for p in ROOT.rglob("*")
            if p.suffix in (".py", ".js", ".html", ".css") and p.is_file()]


def test_all_sources_valid_utf8():
    files = _sources()
    assert files, "no source files found"
    for path in files:
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise AssertionError(f"{path} is not valid UTF-8")


def test_no_mojibake_markers():
    bad = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        hits = MOJIBAKE_RE.findall(text)
        if hits:
            bad.append((str(path), hits[:5]))
    assert not bad, f"mojibake found: {bad}"
