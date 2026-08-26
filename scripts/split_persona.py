#!/usr/bin/env python3
""".claude/agents/<role>.md を personas/<role>.md（本体）と
.claude/agents/<role>.frontmatter.yaml（Claude Code 固有メタデータ）に分割する。
一度分割したら build-agent-md.sh で .claude/agents/<role>.md を再生成できる
（結果は元ファイルとバイト単位で同一になる）。

使い方: split_persona.py <repo_root> <role> [<role> ...]
"""
import pathlib
import sys


def split_one(role: str, agents_dir: pathlib.Path, personas_dir: pathlib.Path) -> None:
    src = agents_dir / f"{role}.md"
    lines = src.read_text().split("\n")
    assert lines[0] == "---", f"{src}: frontmatter開始(---)が1行目にない"
    end = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            end = i
            break
    assert end is not None, f"{src}: frontmatter終了(---)が見つからない"

    fm_lines = lines[1:end]
    body_lines = lines[end + 1:]
    if body_lines and body_lines[0] == "":
        body_lines = body_lines[1:]  # frontmatter直後の空行を1つだけ吸収

    meta_path = agents_dir / f"{role}.frontmatter.yaml"
    meta_path.write_text("\n".join(fm_lines) + "\n")

    persona_path = personas_dir / f"{role}.md"
    persona_path.write_text("\n".join(body_lines))

    print(f"split: {role} -> {meta_path.name}, personas/{persona_path.name}")


def main() -> int:
    if len(sys.argv) < 3:
        print(f"usage: {sys.argv[0]} <repo_root> <role> [<role> ...]", file=sys.stderr)
        return 1
    root = pathlib.Path(sys.argv[1])
    agents_dir = root / ".claude" / "agents"
    personas_dir = root / "personas"
    personas_dir.mkdir(exist_ok=True)
    for role in sys.argv[2:]:
        split_one(role, agents_dir, personas_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
