import re, pathlib
root = pathlib.Path("hushplayer")
pat_name = re.compile(r"rgba\((.*?),\s*([0-9.]+)\)\.name\(\)")
pat_raw = re.compile(r"\{rgba\((.*?),\s*([0-9.]+)\)\}")
changed = []
for path in root.rglob("*.py"):
    text = path.read_text(encoding="utf-8")
    new = pat_name.sub(lambda m: f"css_rgba({m.group(1)}, {m.group(2)})", text)
    new = pat_raw.sub(lambda m: "{css_rgba(" + m.group(1) + ", " + m.group(2) + ")}", new)
    if new != text:
        if "css_rgba" not in text:
            lines = new.splitlines(keepends=True)
            done = False
            for i, line in enumerate(lines):
                if ".core.theme import" in line:
                    lines[i] = line.replace("import ", "import css_rgba, ", 1)
                    done = True
                    break
            if not done:
                lines.insert(0, "from hushplayer.core.theme import css_rgba\n")
            new = "".join(lines)
        path.write_text(new, encoding="utf-8")
        changed.append(str(path))
print(len(changed)); print("\n".join(changed))
