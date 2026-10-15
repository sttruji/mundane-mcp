"""Build the ZIP uploaded to OpenAI's plugin directory (ChatGPT and Codex).

The package is `openai-plugin/`, the OAuth-backed directory plugin; `plugin/`
is the separate API-key plugin for Claude Code and Codex marketplaces and is
never uploaded. The ZIP carries only what the manifests use -- the two
manifests, the skills and the referenced assets -- so nothing else in the
folder (notes, editor files, a stray .env) can ride along into a public
listing. Entries are written with a fixed timestamp, so the same source
always produces byte-identical ZIPs.

  python scripts/build_openai_plugin.py            # -> dist/mundane-openai-plugin-<version>.zip
  python scripts/build_openai_plugin.py --out x.zip
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "openai-plugin"
_EPOCH = (2026, 1, 1, 0, 0, 0)


def package_files(root: Path = ROOT) -> list[str]:
    """Every path the ZIP contains, relative to the package root."""
    manifest = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    interface = manifest["extensions"]["com.openai"]["interface"]
    files = {"plugin.json", "mcp.json"}
    files |= {p.relative_to(root).as_posix() for p in (root / "skills").glob("*/SKILL.md")}
    for key in ("logo", "composerIcon", "logoDark", "composerIconDark"):
        if interface.get(key):
            files.add(interface[key].removeprefix("./"))
    files |= {s.removeprefix("./") for s in interface.get("screenshots", [])}
    return sorted(files)


def build(out: Path, root: Path = ROOT) -> list[str]:
    names = package_files(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, (root / name).read_bytes())
    return names


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    version = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))["version"]
    out = args.out or ROOT.parent / "dist" / f"mundane-openai-plugin-{version}.zip"
    for name in build(out):
        print(" ", name)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
