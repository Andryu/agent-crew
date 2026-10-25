#!/usr/bin/env python3
"""移行状況の表示専用台帳を表示・更新する。queue正本には触れない。"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unicodedata


ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state.json"
TASK_TITLES = {
    "P0": "現状と比較基準の固定",
    "P1": "設定管理の一本化",
    "P2": "指示とhookの整理",
    "P3": "引継ぎの整備",
    "P4": "wealth開発への適用",
    "P5": "速度・品質の比較",
    "P6": "実資産の読み取り",
    "P7": "更新運用",
}
STATUSES = ("未着手", "進行中", "検証中", "判断待ち", "合意待ち", "別マイルストーン", "完了", "未確認")
PANE_ROLES = ("parent", "implementer", "report")


def unconfirmed(reason):
    return {
        "overall": "状態を確認できません",
        "panes": {
            "parent": {"id": "wC:pR", "model": "Astra", "role": "計画判断"},
            "implementer": {"id": "wC:pV", "model": "Sol", "role": "編集検証"},
            "report": {"id": "wC:pW", "model": "Python", "role": "表示のみ"},
        },
        "tasks": {key: {"title": title, "status": "未確認", "current": "", "next": "", "blocker": ""}
                  for key, title in TASK_TITLES.items()},
        "current": "未確認",
        "next": "state.jsonを確認",
        "blocker": reason,
        "updated_at": "未確認",
    }


def plain(value):
    return isinstance(value, str) and not any(
        ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value
    )


def read_state():
    try:
        if STATE.is_symlink():
            raise ValueError("state.jsonがsymlinkです")
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") != 1:
            raise ValueError("schemaが不正です")
        for key in ("overall", "current", "next", "blocker", "updated_at"):
            if not plain(data.get(key)):
                raise ValueError(f"{key}が不正です")
        if datetime.fromisoformat(data["updated_at"]).tzinfo is None:
            raise ValueError("updated_atにタイムゾーンがありません")
        panes = data.get("panes")
        if not isinstance(panes, dict) or any(
            not isinstance(panes.get(role), dict)
            or any(not plain(panes[role].get(key)) for key in ("id", "model", "role"))
            for role in PANE_ROLES
        ):
            raise ValueError("担当paneが不正です")
        tasks = data.get("tasks")
        if not isinstance(tasks, dict) or set(tasks) != set(TASK_TITLES):
            raise ValueError("P0〜P7の一覧が不正です")
        for key in TASK_TITLES:
            task = tasks[key]
            if not isinstance(task, dict) or task.get("status") not in STATUSES or any(
                not plain(task.get(field)) for field in ("title", "current", "next", "blocker")
            ):
                raise ValueError(f"{key}が不正です")
        return data, None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return unconfirmed("state.jsonが不正または読取不能"), str(exc)


def cell_width(char):
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in "WF" else 1


def fit(text, width):
    if width <= 0:
        return ""
    result = []
    used = 0
    for char in text:
        step = cell_width(char)
        if used + step > width:
            break
        result.append(char)
        used += step
    if len(result) < len(text) and width > 1:
        while result and used + 1 > width:
            used -= cell_width(result.pop())
        result.append("…")
    return "".join(result)


def render(data, columns, rows):
    panes = data["panes"]
    lines = [
        "Codex移行 進捗ボード",
        "表示専用台帳 / queue正本ではありません / queue自動更新なし",
        f"全体: {data['overall']}",
        f"親: {panes['parent']['id']}  {panes['parent']['model']} / {panes['parent']['role']}",
        f"実装: {panes['implementer']['id']}  {panes['implementer']['model']} / {panes['implementer']['role']}",
        f"報告: {panes['report']['id']}  {panes['report']['model']} / {panes['report']['role']}",
        "P0〜P7:",
    ]
    for key in TASK_TITLES:
        task = data["tasks"][key]
        lines.append(f" {key} [{task['status']}] {task['title']}")
    lines.extend((
        f"現在: {data['current']}",
        f"次: {data['next']}",
        f"親への判断待ち: {data['blocker']}",
        f"更新: {data['updated_at']}",
    ))
    if rows < len(lines):
        # 極端に低いpaneでは次の再描画でページを切り替える。
        top = lines[:6]
        rest = lines[6:]
        room = max(0, rows - len(top) - 1)
        if room:
            page = int(time.monotonic() // 3) % max(1, (len(rest) + room - 1) // room)
            lines = top + [f"続き {page + 1}"] + rest[page * room:(page + 1) * room]
        else:
            lines = lines[:rows]
    return "\n".join(fit(line, columns) for line in lines[:rows])


def atomic_write(data):
    if STATE.is_symlink():
        raise ValueError("state.jsonがsymlinkです")
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=ROOT, prefix=".state-", delete=False) as handle:
            name = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, STATE)
        name = None
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


def set_state(args, parser):
    if all(getattr(args, key) is None for key in ("status", "overall", "current", "next", "blocker")):
        parser.error("更新項目を指定してください")
    if args.status and not args.task:
        parser.error("--statusには--taskが必要です")
    if args.status == "完了" and not args.accepted:
        parser.error("完了には親の受入確認後に--acceptedが必要です")
    if args.accepted and args.status != "完了":
        parser.error("--acceptedは--status 完了のときだけ指定できます")
    data, error = read_state()
    if error:
        parser.error(f"状態が不正なため更新しません: {error}")
    updates = {key: getattr(args, key) for key in ("overall", "current", "next", "blocker")
               if getattr(args, key) is not None}
    if any(not plain(value) for value in updates.values()):
        parser.error("改行・制御文字は入力できません")
    if args.task:
        if args.status:
            data["tasks"][args.task]["status"] = args.status
        for key in ("current", "next", "blocker"):
            if key in updates:
                data["tasks"][args.task][key] = updates[key]
                data[key] = updates[key]
        if "overall" in updates:
            data["overall"] = updates["overall"]
    else:
        data.update(updates)
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        atomic_write(data)
    except (OSError, ValueError) as exc:
        parser.error(f"更新できません: {exc}")
    print(f"表示台帳を更新: {args.task or '全体'}")


def main():
    parser = argparse.ArgumentParser(description="移行進捗の表示専用台帳。queue正本は更新しません。")
    parser.add_argument("--once", action="store_true", help="1回表示して終了")
    sub = parser.add_subparsers(dest="command")
    update = sub.add_parser("set", help="state.jsonだけを原子的に更新")
    update.add_argument("--task", choices=tuple(TASK_TITLES))
    update.add_argument("--status", choices=STATUSES)
    update.add_argument("--overall")
    update.add_argument("--current")
    update.add_argument("--next")
    update.add_argument("--blocker")
    update.add_argument("--accepted", action="store_true", help="親の受入確認済みで完了を記録")
    args = parser.parse_args()
    if args.command == "set":
        set_state(args, update)
        return
    if args.once:
        data, _ = read_state()
        size = shutil.get_terminal_size(fallback=(80, 24))
        print(render(data, size.columns, size.lines))
        return
    try:
        while True:
            data, _ = read_state()
            size = shutil.get_terminal_size(fallback=(80, 24))
            sys.stdout.write("\x1b[2J\x1b[H" + render(data, size.columns, size.lines))
            sys.stdout.flush()
            time.sleep(3)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
