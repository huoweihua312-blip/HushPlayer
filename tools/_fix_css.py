import re, pathlib
root = pathlib.Path("hushplayer")
pat_name = re.compile(r"rgba\(([^()]*?),\s*([0-9.]+)\)\.name\(\)")
pat_raw = re.compile(r"\{rgba\(([^()]*?),\s*([0-9.]+)\)\}")
changed = []
for path in root.rglob("*.py"):
    text = path.read_text(encoding="utf-8")
    new = pat_name.sub(lambda m: f"css_rgba({m.group(1)}, {m.group(2)})", text)
    new = pat_raw.sub(lambda m: "{css_rgba(" + m.group(1) + ", " + m.group(2) + ")}", new)
    if new != text:
        # make sure css_rgba is imported
        if "css_rgba" not in text:
            lines = new.splitlines(keepends=True)
            for i, line in enumerate(lines):
                if line.startswith("from ...core.theme import") or line.startswith("from ..core.theme import") or line.startswith("from .core.theme import"):
                    if "css_rgba" not in line:
                        lines[i] = line.replace("import ", "import css_rgba, ", 1)
                    break
            else:
                lines.insert(0, "from hushplayer.core.theme import css_rgba\n")
            new = "".join(lines)
        path.write_text(new, encoding="utf-8")
        changed.append(str(path))
print("\n".join(changed))
