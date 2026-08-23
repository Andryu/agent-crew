#!/usr/bin/env python3
"""02 共通チェッカー。振る舞い（生成物の構造）だけを見る。

使い方: _check.py <check-name>
環境変数: BENCH_WORK_DIR / BENCH_SEED
"""
from __future__ import annotations

import os
import random
import re
import subprocess
import sys
from pathlib import Path

WORK = Path(os.environ["BENCH_WORK_DIR"]).resolve()
SEED = int(os.environ.get("BENCH_SEED", "12345"))
AGENT_DIR = WORK / ".claude" / "agents"
TARGET_NAME = "viral-video-researcher"

# 「既存コードの編集」「コマンド実行」にあたる道具（リサーチ専任には持たせない）
FORBIDDEN_TOOLS = {
    "Edit", "MultiEdit", "NotebookEdit", "Bash", "BashOutput", "KillShell",
    "KillBash", "Execute", "Shell", "Task", "Agent", "SlashCommand",
}
# 読み取り・調査系（最低1つは必要）
RESEARCH_TOOLS = {"Read", "Glob", "Grep", "WebSearch", "WebFetch"}


def die(msg: str) -> "None":
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def git(*args: str) -> str:
    p = subprocess.run(["git", "-C", str(WORK), *args],
                       capture_output=True, text=True)
    if p.returncode != 0:
        die("git %s に失敗: %s" % (" ".join(args), p.stderr.strip()))
    return p.stdout


def root_commit() -> str:
    out = git("rev-list", "--max-parents=0", "HEAD").split()
    if not out:
        die("初期コミットが見つからない（作業ディレクトリが壊れている）")
    return out[-1]


def baseline_agent_files() -> "dict":
    """setup 時点（初期コミット）に存在したエージェント定義ファイル -> 内容(bytes)"""
    root = root_commit()
    names = [n for n in git("ls-tree", "-r", "--name-only", root,
                            ".claude/agents/").splitlines() if n.endswith(".md")]
    out = {}
    for n in names:
        p = subprocess.run(["git", "-C", str(WORK), "show", "%s:%s" % (root, n)],
                           capture_output=True)
        if p.returncode != 0:
            die("初期スナップショットの %s を読めない" % n)
        out[n] = p.stdout
    return out


def current_agent_files() -> "list":
    if not AGENT_DIR.is_dir():
        die(".claude/agents/ ディレクトリが無い")
    rel = []
    for p in sorted(AGENT_DIR.rglob("*.md")):
        rel.append(str(p.relative_to(WORK)))
    return rel


def split_frontmatter(text: str):
    """先頭 --- ... --- を (キー順リスト, dict, 本文) に分解する。無ければ None。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    keys, data = [], {}
    cur = None
    for raw in lines[1:end]:
        if not raw.strip():
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", raw)
        if m and not raw.startswith((" ", "\t")):
            cur = m.group(1)
            keys.append(cur)
            val = m.group(2).strip()
            if val in (">-", ">", "|", "|-", ">+", "|+"):
                val = ""
            data[cur] = val
        elif cur is not None:
            data[cur] = (data[cur] + " " + raw.strip()).strip()
    return keys, data, "\n".join(lines[end + 1:])


def new_agent_file():
    base = baseline_agent_files()
    cur = current_agent_files()
    new = [p for p in cur if p not in base]
    if not new:
        die("エージェント定義が1つも追加されていない")
    if len(new) > 1:
        die("追加されたエージェント定義が複数ある: %s" % ", ".join(new))
    path = WORK / new[0]
    text = path.read_text(encoding="utf-8")
    fm = split_frontmatter(text)
    if fm is None:
        die("追加ファイル %s の先頭に frontmatter が無い" % new[0])
    return new[0], fm[0], fm[1], fm[2]


def baseline_schema():
    """既存エージェント定義から frontmatter の項目構成を抽出する（シードで部分集合を選ぶ）"""
    base = baseline_agent_files()
    parsed = {}
    for name, blob in base.items():
        fm = split_frontmatter(blob.decode("utf-8", "replace"))
        if fm is not None:
            parsed[name] = fm
    if len(parsed) < 3:
        die("既存エージェント定義が少なすぎてスキーマを抽出できない")
    rnd = random.Random(SEED)
    names = sorted(parsed)
    k = max(3, len(names) // 2)
    sample = rnd.sample(names, k)
    keysets = [frozenset(parsed[n][0]) for n in sample]
    inter = set(keysets[0]).intersection(*keysets[1:])
    union = set().union(*keysets)
    if inter != union:
        die("既存定義から一貫したスキーマを抽出できなかった（ベンチ側の異常）")
    models = set()
    for n in names:
        v = parsed[n][1].get("model")
        if v:
            models.add(v)
    return inter, models


def tool_list(data) -> "list":
    raw = data.get("tools", "")
    return [t.strip() for t in raw.replace("\n", ",").split(",") if t.strip()]


# ---------- 個別チェック ----------

def check_regression():
    """既存エージェント定義が1つも変更・削除されていないこと"""
    base = baseline_agent_files()
    rnd = random.Random(SEED ^ 0x5EED)
    order = sorted(base)
    rnd.shuffle(order)
    for name in order:
        p = WORK / name
        if not p.is_file():
            die("既存のエージェント定義が消えている: %s" % name)
        if p.read_bytes() != base[name]:
            die("既存のエージェント定義が書き換えられている: %s" % name)


def check_schema():
    path, keys, data, _body = new_agent_file()
    schema, _models = baseline_schema()
    got = set(keys)
    if got != schema:
        die("frontmatter の項目構成が既存と違う（不足: %s / 余分: %s）"
            % (sorted(schema - got) or "なし", sorted(got - schema) or "なし"))
    if len(keys) != len(set(keys)):
        die("frontmatter に同じ項目が複数ある")
    for k in keys:
        if not str(data.get(k, "")).strip():
            die("frontmatter の %s が空" % k)


def check_name():
    path, _keys, data, _body = new_agent_file()
    stem = Path(path).stem
    if data.get("name") != stem:
        die("name(%r) がファイル名(%r)と一致しない" % (data.get("name"), stem))
    if data.get("name") != TARGET_NAME:
        die("name が %r になっていない: %r" % (TARGET_NAME, data.get("name")))
    if str(Path(path).parent).replace("\\", "/") != ".claude/agents":
        die("追加ファイルの置き場所が既存と違う: %s" % path)


def check_tools():
    _path, _keys, data, _body = new_agent_file()
    tools = tool_list(data)
    # まず正常系: 道具が列挙されていて、調査に使えるものが含まれること
    if not tools:
        die("tools が空")
    bad = [t for t in tools if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", t)]
    if bad:
        die("道具名として解釈できない値がある: %s" % bad)
    if not (set(tools) & RESEARCH_TOOLS):
        die("調査に使える道具(%s のいずれか)が1つも無い" % sorted(RESEARCH_TOOLS))
    # 本題: 編集・実行系が含まれないこと
    hit = sorted(set(tools) & FORBIDDEN_TOOLS)
    if hit:
        die("編集・実行にあたる道具が含まれている: %s" % hit)


def check_model():
    _path, _keys, data, _body = new_agent_file()
    _schema, models = baseline_schema()
    if not models:
        die("既存定義から model の候補を抽出できなかった（ベンチ側の異常）")
    if data.get("model") not in models:
        die("model が既存定義に存在しない値: %r（既存: %s）"
            % (data.get("model"), sorted(models)))


def check_description():
    _path, _keys, data, _body = new_agent_file()
    d = data.get("description", "")
    if len(d) < 60:
        die("description が短すぎる（%d文字）" % len(d))
    quoted = re.findall(r"[「『]([^」』]{2,})[」』]", d)
    if len(quoted) < 2:
        die("依頼の言い方の例（「」付き）が2つ未満: %d" % len(quoted))
    if not any("Nagi" in q for q in quoted):
        die("呼び名(Nagi)を含む依頼例が無い")
    if "起動" not in d:
        die("description に「起動」が無い")
    if "動画" not in d:
        die("description に対象領域（動画）の語が無い")
    low = d.lower()
    plat = [p for p in ("tiktok", "youtube", "instagram") if p in low]
    if len(plat) < 2:
        die("対象プラットフォームへの言及が2つ未満: %s" % plat)


def check_body():
    _path, _keys, _data, body = new_agent_file()
    heads = [ln for ln in body.splitlines() if re.match(r"^#{1,3}\s+\S", ln)]
    if len(heads) < 4:
        die("本文の見出しが4つ未満: %d" % len(heads))
    nonempty = [ln for ln in body.splitlines() if ln.strip()]
    if len(nonempty) < 25:
        die("本文の中身が薄い（非空行 %d 行）" % len(nonempty))


CHECKS = {
    "regression": check_regression,
    "schema": check_schema,
    "name": check_name,
    "tools": check_tools,
    "model": check_model,
    "description": check_description,
    "body": check_body,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in CHECKS:
        print("usage: _check.py {%s}" % "|".join(CHECKS), file=sys.stderr)
        sys.exit(2)
    CHECKS[sys.argv[1]]()
    print("PASS")
