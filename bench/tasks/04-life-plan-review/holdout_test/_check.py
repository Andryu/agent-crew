#!/usr/bin/env python3
"""04 共通チェッカー。生成物の構造と参照の解決だけを見る。

使い方: _check.py <check-name>
環境変数: BENCH_WORK_DIR / BENCH_SEED / BENCH_TMP
"""
from __future__ import annotations

import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

WORK = Path(os.environ["BENCH_WORK_DIR"]).resolve()
TMP = Path(os.environ.get("BENCH_TMP", "/tmp")).resolve()
SEED = int(os.environ.get("BENCH_SEED", "12345"))
SKILLS_REL = ".claude/skills"
TARGET = "life-plan-review"
EXISTING = "life-planner"


def die(msg: str) -> None:
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def git(*args: str) -> str:
    p = subprocess.run(["git", "-C", str(WORK), *args], capture_output=True, text=True)
    if p.returncode != 0:
        die("git %s に失敗: %s" % (" ".join(args), p.stderr.strip()))
    return p.stdout


def root_commit() -> str:
    out = git("rev-list", "--max-parents=0", "HEAD").split()
    if not out:
        die("初期コミットが見つからない")
    return out[-1]


def baseline_blobs(prefix: str) -> dict:
    root = root_commit()
    names = [n for n in git("ls-tree", "-r", "--name-only", root, prefix).splitlines() if n]
    out = {}
    for n in names:
        p = subprocess.run(["git", "-C", str(WORK), "show", "%s:%s" % (root, n)],
                           capture_output=True)
        if p.returncode != 0:
            die("初期スナップショットの %s を読めない" % n)
        out[n] = p.stdout
    return out


def split_frontmatter(text: str):
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
    keys, data, cur = [], {}, None
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


def skill_dir() -> Path:
    d = WORK / SKILLS_REL / TARGET
    if not d.is_dir():
        die("%s/%s/ が無い" % (SKILLS_REL, TARGET))
    return d


def skill_md() -> "tuple":
    d = skill_dir()
    f = d / "SKILL.md"
    if not f.is_file():
        die("%s/%s/SKILL.md が無い" % (SKILLS_REL, TARGET))
    fm = split_frontmatter(f.read_text(encoding="utf-8"))
    if fm is None:
        die("SKILL.md の先頭に frontmatter が無い")
    return d, f, fm[0], fm[1], fm[2]


# 相対パスで書かれた md/ファイル参照をバッククォート内から拾う
REF_RE = re.compile(r"`([^`\n]*?\.(?:md|markdown|txt|json|yaml|yml|sh|py))`")


def collect_refs(md_file: Path) -> list:
    text = md_file.read_text(encoding="utf-8")
    refs = []
    for m in REF_RE.finditer(text):
        raw = m.group(1).strip()
        if not raw or raw.startswith(("http://", "https://", "notion://")):
            continue
        if "/" not in raw and not raw.startswith("."):
            # 単なるファイル名の言及（SKILL.md 等）はパス参照とみなさない
            continue
        refs.append(raw)
    return refs


# ---------- 個別チェック ----------

def check_regression():
    """既存スキル（life-planner）のファイルが1つも変更・削除されていないこと"""
    base = baseline_blobs(SKILLS_REL + "/" + EXISTING)
    if not base:
        die("初期スナップショットに既存スキルが無い（ベンチ側の異常）")
    rnd = random.Random(SEED ^ 0x04)
    order = sorted(base)
    rnd.shuffle(order)
    for name in order:
        p = WORK / name
        if not p.is_file():
            die("既存スキルのファイルが消えている: %s" % name)
        if p.read_bytes() != base[name]:
            die("既存スキルのファイルが書き換えられている: %s" % name)


def check_name():
    d, _f, _keys, data, _body = skill_md()
    if data.get("name") != d.name:
        die("name(%r) がディレクトリ名(%r)と一致しない" % (data.get("name"), d.name))
    if not str(data.get("description", "")).strip():
        die("description が空")


def check_description_positive():
    _d, _f, _keys, data, _body = skill_md()
    desc = data.get("description", "")
    quoted = re.findall(r"[「『]([^」』]{2,})[」』]", desc)
    if len(quoted) < 3:
        die("依頼の言い方の例（「」付き）が3つ未満: %d" % len(quoted))
    groups = {
        "定期性": ("定期", "周期", "半年", "毎年", "年に一度", "定点"),
        "見直し": ("見直", "振り返", "棚卸", "レビュー"),
        "資産形成": ("資産", "NISA", "iDeCo", "積立", "純資産"),
    }
    missing = [g for g, words in groups.items() if not any(w in desc for w in words)]
    if missing:
        die("description に %s を表す語が無い" % "・".join(missing))


def check_description_boundary():
    _d, _f, _keys, data, _body = skill_md()
    desc = data.get("description", "")
    # 前提確認（空虚な合格の防止）: まず使う場面がきちんと書かれていること
    if len(desc) < 80:
        die("description が短すぎて境界条件を判定できない（%d文字）" % len(desc))
    if not re.search(r"[「『][^」』]{2,}[」』]", desc):
        die("依頼の言い方の例が無い状態で境界だけ書かれている")
    # 本題: 初回作成は既存スキルの担当であることが書かれていること
    if EXISTING not in desc:
        die("description に既存スキル名(%s)への言及が無い" % EXISTING)
    if not any(w in desc for w in ("初回", "初めて", "一度も", "新規作成")):
        die("description に「初回作成は対象外」であることが書かれていない")
    if not any(w in desc for w in ("担当", "使わない", "対象外", "誘導", "そちら")):
        die("description に担当分けを示す語が無い")


def check_references():
    d, f, _keys, _data, _body = skill_md()
    refs = collect_refs(f)
    if not refs:
        die("SKILL.md から参照されている資料が1つも無い")
    ref_dir = d / "references"
    if not ref_dir.is_dir():
        die("references/ ディレクトリが無い")
    ref_files = sorted(p for p in ref_dir.rglob("*") if p.is_file())
    if not ref_files:
        die("references/ が空")

    # 1) 参照はすべて相対パスで、実在すること（絶対パスは不可）
    for r in refs:
        if r.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", r):
            die("絶対パスで参照している: %s" % r)
        target = (f.parent / r).resolve()
        if not target.exists():
            die("参照先が実在しない: %s" % r)

    # 2) references/ に置いた資料はすべて SKILL.md から参照されていること
    for p in ref_files:
        rel = p.relative_to(d).as_posix()
        if not any(r.replace("./", "").endswith(rel) for r in refs):
            die("references/ の資料が SKILL.md から参照されていない: %s" % rel)

    # 3) スキル置き場ごと別の場所へ移しても参照が壊れないこと（相対性の実証）
    rnd = random.Random(SEED)
    moved_root = TMP / ("relocated-%06d" % rnd.randrange(10 ** 6)) / "nested"
    moved_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(WORK / SKILLS_REL, moved_root / "skills")
    moved_md = moved_root / "skills" / TARGET / "SKILL.md"
    for r in collect_refs(moved_md):
        if not (moved_md.parent / r).resolve().exists():
            die("移設後に参照が壊れた（相対パスになっていない）: %s" % r)


PII = [
    (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "メールアドレス"),
    (r"/Users/[A-Za-z0-9_.\-]+/", "個人のホームディレクトリのパス"),
    (r"/home/[A-Za-z0-9_.\-]+/", "個人のホームディレクトリのパス"),
    (r"0[789]0[\-‐ ]?[0-9]{4}[\-‐ ]?[0-9]{4}", "電話番号"),
    (r"https?://(?:www\.)?notion\.so/\S+", "特定ユーザーの Notion URL"),
    (r"\b[0-9a-f]{32}\b", "Notion のページ/DB ID らしき32桁の16進"),
]


def check_no_pii():
    d, _f, _keys, _data, _body = skill_md()
    files = sorted(p for p in d.rglob("*") if p.is_file())
    if not files:
        die("スキルのファイルが1つも無い")
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for pat, label in PII:
            m = re.search(pat, text)
            if m:
                line = text[:m.start()].count("\n") + 1
                die("%s に%sらしき記述: %s:%d" % (p.relative_to(WORK), label,
                                                p.name, line))


def check_body():
    d, _f, _keys, _data, body = skill_md()
    heads = [ln for ln in body.splitlines() if re.match(r"^#{1,4}\s+\S", ln)]
    if len(heads) < 4:
        die("SKILL.md 本文の見出しが4つ未満: %d" % len(heads))
    nonempty = [ln for ln in body.splitlines() if ln.strip()]
    if len(nonempty) < 30:
        die("SKILL.md 本文の中身が薄い（非空行 %d 行）" % len(nonempty))
    steps = [ln for ln in body.splitlines() if re.match(r"^#{2,4}\s*(?:ステップ)?\s*\d", ln)]
    if len(steps) < 3:
        die("見直しの手順がステップに分かれていない（番号付き見出し %d 個）" % len(steps))
    ref_md = sorted((d / "references").rglob("*.md")) if (d / "references").is_dir() else []
    if not ref_md:
        die("references/ に資料が無い")
    if max(len(p.read_text(encoding="utf-8").splitlines()) for p in ref_md) < 20:
        die("references/ の資料が薄すぎる")


CHECKS = {
    "regression": check_regression,
    "name": check_name,
    "description_positive": check_description_positive,
    "description_boundary": check_description_boundary,
    "references": check_references,
    "no_pii": check_no_pii,
    "body": check_body,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in CHECKS:
        print("usage: _check.py {%s}" % "|".join(CHECKS), file=sys.stderr)
        sys.exit(2)
    CHECKS[sys.argv[1]]()
    print("PASS")
