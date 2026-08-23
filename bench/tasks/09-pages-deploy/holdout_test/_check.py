#!/usr/bin/env python3
"""09 共通チェッカー。

Actions は実行しない。workflow を YAML として構造で読み、
ビルド手順（run ブロック）だけを sandbox で実際に走らせて成果物の配置を検証する。
ステップ名・ステップ数・実装手段は問わない（振る舞いのみを採点する）。

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

import yaml

WORK = Path(os.environ["BENCH_WORK_DIR"]).resolve()
TMP = Path(os.environ.get("BENCH_TMP", "/tmp")).resolve()
SEED = int(os.environ.get("BENCH_SEED", "12345"))

WF_DIR = WORK / ".github" / "workflows"
MAIN_BRANCH = "main"
GAME_BRANCH = "research/game-department-prototype"
GAME_SRC_SUBDIR = "game-prototype/loop-room"
DASH_APP = "dashboard/app/index.html"
DASH_DEMO = "dashboard/prototype/stonefish-dashboard.html"


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


def load_new_workflow():
    """setup 後に追加された workflow を1つ選び、(パス, パース結果) を返す"""
    base = set(baseline_blobs(".github/workflows"))
    if not WF_DIR.is_dir():
        die(".github/workflows/ が無い")
    cur = [str(p.relative_to(WORK)) for p in sorted(WF_DIR.iterdir())
           if p.is_file() and p.suffix in (".yml", ".yaml")]
    new = [n for n in cur if n not in base]
    if not new:
        die("workflow が追加されていない")
    # 複数ある場合は Pages 関連（pages 権限を持つ）ものを選ぶ
    parsed = []
    for n in new:
        try:
            doc = yaml.safe_load((WORK / n).read_text(encoding="utf-8"))
        except Exception as e:
            die("%s が YAML として読めない: %s" % (n, e))
        if not isinstance(doc, dict):
            die("%s が map になっていない" % n)
        parsed.append((n, doc))
    if len(parsed) > 1:
        pages = [x for x in parsed
                 if "pages" in str(x[1].get("permissions", "")).lower()]
        if pages:
            parsed = pages
    return parsed[0]


def get_on(doc: dict):
    for key in ("on", True, "True"):
        if key in doc:
            return doc[key]
    die("workflow に on: が無い")


def all_steps(doc: dict) -> list:
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        die("workflow に jobs が無い")
    steps = []
    for _name, job in jobs.items():
        if isinstance(job, dict):
            for s in (job.get("steps") or []):
                if isinstance(s, dict):
                    steps.append(s)
    if not steps:
        die("workflow に steps が無い")
    return steps


def uses_of(step: dict) -> str:
    return str(step.get("uses") or "")


def checkout_steps(doc: dict) -> list:
    return [s for s in all_steps(doc) if "actions/checkout" in uses_of(s)]


def norm_path(v) -> str:
    s = str(v or ".").strip()
    s = s.rstrip("/")
    if s.startswith("./"):
        s = s[2:]
    return s or "."


# ---------- sandbox ビルド ----------

EXPR_RE = re.compile(r"\$\{\{[^}]*\}\}")


def build_in_sandbox():
    """checkout ステップの path/ref に合わせてソースを配置し、run ブロックを実行する"""
    _name, doc = load_new_workflow()
    cos = checkout_steps(doc)
    if len(cos) < 2:
        die("ソースを2か所からチェックアウトしていない（checkout ステップ %d 個）" % len(cos))

    rnd = random.Random(SEED)
    marker = "BENCHMARK-%08d" % rnd.randrange(10 ** 8)

    sandbox = TMP / ("sandbox-%06d" % rnd.randrange(10 ** 6))
    if sandbox.exists():
        shutil.rmtree(sandbox)
    sandbox.mkdir(parents=True)

    dash_app_src = WORK / DASH_APP
    dash_demo_src = WORK / DASH_DEMO
    if not dash_app_src.is_file():
        die("%s が無い" % DASH_APP)
    if not dash_demo_src.is_file():
        die("%s が無い" % DASH_DEMO)

    placed = {}
    for s in cos:
        with_ = s.get("with") or {}
        ref = str(with_.get("ref") or MAIN_BRANCH).strip()
        path = norm_path(with_.get("path"))
        dest = sandbox / path
        dest.mkdir(parents=True, exist_ok=True)
        if ref == GAME_BRANCH:
            game = dest / GAME_SRC_SUBDIR
            (game / "js").mkdir(parents=True, exist_ok=True)
            (game / "index.html").write_text(
                "<!doctype html><title>loop-room</title>\n<!-- %s-GAME -->\n" % marker,
                encoding="utf-8")
            (game / "style.css").write_text("body{/* %s-CSS */}\n" % marker, encoding="utf-8")
            (game / "js" / "main.js").write_text("// %s-JS\n" % marker, encoding="utf-8")
            (game / "README.md").write_text("# loop-room %s\n" % marker, encoding="utf-8")
            placed["game"] = path
        else:
            app = dest / DASH_APP
            demo = dest / DASH_DEMO
            app.parent.mkdir(parents=True, exist_ok=True)
            demo.parent.mkdir(parents=True, exist_ok=True)
            app.write_text(dash_app_src.read_text(encoding="utf-8", errors="replace")
                           + "\n<!-- %s-APP -->\n" % marker, encoding="utf-8")
            demo.write_text(dash_demo_src.read_text(encoding="utf-8", errors="replace")
                            + "\n<!-- %s-DEMO -->\n" % marker, encoding="utf-8")
            placed["main"] = path

    if "game" not in placed:
        die("ゲーム側ブランチ(%s)を ref に指定した checkout が無い" % GAME_BRANCH)
    if "main" not in placed:
        die("%s ブランチを ref に指定した checkout が無い" % MAIN_BRANCH)

    # 全 run ブロックを順に連結して実行する（ステップ名・分割の仕方は問わない）
    lines = ["set -e"]
    found_run = False
    for s in all_steps(doc):
        run = s.get("run")
        if not run:
            continue
        found_run = True
        body = EXPR_RE.sub("", str(run))
        wd = s.get("working-directory")
        if wd:
            lines.append("( cd %s" % EXPR_RE.sub("", str(wd)))
            lines.append(body)
            lines.append(")")
        else:
            lines.append(body)
    if not found_run:
        die("サイトを組み立てる手順（run）が1つも無い")

    script = sandbox / "_bench_build.sh"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    p = subprocess.run(["bash", str(script)], cwd=str(sandbox),
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        die("ビルド手順が失敗した（exit %d）\n--- stdout ---\n%s\n--- stderr ---\n%s"
            % (p.returncode, p.stdout[-1500:], p.stderr[-1500:]))
    return sandbox, marker


# ---------- 個別チェック ----------

def check_regression():
    """既存の workflow / ダッシュボードの元ファイルが壊れていないこと"""
    base = baseline_blobs(".github/workflows")
    if not base:
        die("初期スナップショットに既存 workflow が無い（ベンチ側の異常）")
    rnd = random.Random(SEED ^ 0x09)
    order = sorted(base)
    rnd.shuffle(order)
    for name in order:
        p = WORK / name
        if not p.is_file():
            die("既存の workflow が消えている: %s" % name)
        if p.read_bytes() != base[name]:
            die("既存の workflow が書き換えられている: %s" % name)
        try:
            yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:
            die("既存の workflow が YAML として壊れている: %s (%s)" % (name, e))
    for rel in (DASH_APP, DASH_DEMO):
        if not (WORK / rel).is_file():
            die("既存のダッシュボードのファイルが消えている: %s" % rel)


def check_triggers():
    _name, doc = load_new_workflow()
    on = get_on(doc)
    if not isinstance(on, dict):
        die("on: が map になっていない")
    push = on.get("push")
    if not isinstance(push, dict):
        die("on.push が無い")
    branches = push.get("branches") or []
    if isinstance(branches, str):
        branches = [branches]
    branches = [str(b) for b in branches]
    for b in (MAIN_BRANCH, GAME_BRANCH):
        if b not in branches:
            die("on.push.branches に %s が入っていない: %s" % (b, branches))


def check_dual_checkout():
    _name, doc = load_new_workflow()
    cos = checkout_steps(doc)
    if len(cos) < 2:
        die("checkout ステップが2つ未満: %d" % len(cos))
    refs, paths = [], []
    for s in cos:
        with_ = s.get("with") or {}
        refs.append(str(with_.get("ref") or MAIN_BRANCH).strip())
        paths.append(norm_path(with_.get("path")))
    for b in (MAIN_BRANCH, GAME_BRANCH):
        if b not in refs:
            die("ref に %s を指定した checkout が無い: %s" % (b, refs))
    if len(set(paths)) < 2:
        die("チェックアウト先が衝突している: %s" % paths)


def check_permissions():
    _name, doc = load_new_workflow()
    perms = doc.get("permissions")
    if not isinstance(perms, dict):
        jobs = doc.get("jobs") or {}
        for _n, job in jobs.items():
            if isinstance(job, dict) and isinstance(job.get("permissions"), dict):
                perms = job["permissions"]
                break
    if not isinstance(perms, dict):
        die("permissions が設定されていない")
    if str(perms.get("pages", "")).lower() != "write":
        die("permissions.pages が write でない: %r" % perms.get("pages"))
    if str(perms.get("id-token", "")).lower() != "write":
        die("permissions.id-token が write でない: %r" % perms.get("id-token"))


def check_concurrency():
    _name, doc = load_new_workflow()
    conc = doc.get("concurrency")
    if conc is None:
        jobs = doc.get("jobs") or {}
        for _n, job in jobs.items():
            if isinstance(job, dict) and job.get("concurrency") is not None:
                conc = job["concurrency"]
                break
    if conc is None:
        die("concurrency が設定されていない")
    group = conc if isinstance(conc, str) else (conc or {}).get("group")
    if not str(group or "").strip():
        die("concurrency.group が空")


def check_artifact_path():
    _name, doc = load_new_workflow()
    ups = [s for s in all_steps(doc) if "upload-pages-artifact" in uses_of(s)]
    if not ups:
        die("Pages のアーティファクトをアップロードするステップが無い")
    for s in ups:
        with_ = s.get("with") or {}
        if norm_path(with_.get("path")) != "_site":
            die("アップロード対象が _site でない: %r" % with_.get("path"))


def check_build_layout():
    sandbox, marker = build_in_sandbox()
    site = sandbox / "_site"
    if not site.is_dir():
        die("_site が作られていない（sandbox の中身: %s）"
            % sorted(p.name for p in sandbox.iterdir()))

    game_index = site / "index.html"
    if not game_index.is_file():
        die("_site/index.html（ゲーム）が無い")
    if ("%s-GAME" % marker) not in game_index.read_text(encoding="utf-8", errors="replace"):
        die("_site/index.html がゲーム側の内容になっていない")
    if not (site / "style.css").is_file() or not (site / "js" / "main.js").is_file():
        die("ゲームの付随ファイル（style.css / js/main.js）がルートに配置されていない")

    dash_index = site / "dashboard" / "index.html"
    if not dash_index.is_file():
        die("_site/dashboard/index.html が無い")
    if ("%s-APP" % marker) not in dash_index.read_text(encoding="utf-8", errors="replace"):
        die("_site/dashboard/index.html が実データ版の内容になっていない")

    demo = site / "dashboard" / "demo.html"
    if not demo.is_file():
        die("_site/dashboard/demo.html が無い")
    if ("%s-DEMO" % marker) not in demo.read_text(encoding="utf-8", errors="replace"):
        die("_site/dashboard/demo.html がデモ版の内容になっていない")


def check_demo_link():
    sandbox, marker = build_in_sandbox()
    dash_index = sandbox / "_site" / "dashboard" / "index.html"
    if not dash_index.is_file():
        die("_site/dashboard/index.html が無い（前提が満たせていない）")
    text = dash_index.read_text(encoding="utf-8", errors="replace")
    if ("%s-APP" % marker) not in text:
        die("_site/dashboard/index.html が実データ版の内容になっていない（前提）")
    if "demo.html" not in text:
        die("実データ版のページから demo.html への導線が無い")
    if re.search(r"""["'](?:/|https?://)[^"']*demo\.html""", text):
        die("demo.html への参照が絶対パス/絶対URLになっている")


CHECKS = {
    "regression": check_regression,
    "triggers": check_triggers,
    "dual_checkout": check_dual_checkout,
    "permissions": check_permissions,
    "concurrency": check_concurrency,
    "artifact_path": check_artifact_path,
    "build_layout": check_build_layout,
    "demo_link": check_demo_link,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in CHECKS:
        print("usage: _check.py {%s}" % "|".join(CHECKS), file=sys.stderr)
        sys.exit(2)
    CHECKS[sys.argv[1]]()
    print("PASS")
