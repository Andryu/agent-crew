#!/usr/bin/env python3
"""所有するCodex TOML区画だけを合成する。実設定への適用は明示指定時のみ。"""

import argparse
import copy
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import fcntl
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parents[1]
TOP = ("approval_policy", "approvals_reviewer", "default_permissions")
LEGACY_START = "# BEGIN wealth-advisor developer permissions\n"
LEGACY_END = "# END wealth-advisor developer permissions\n"
KNOWN_UNMARKED_LEGACY_SHA256 = "17081a191d7766934a755dcab6e2d1ecb27a3ac79045399780742a73c4aaf61a"
HEADER = re.compile(r"^\s*(\[\[?.*?\]\]?)\s*(?:#.*)?$")


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _path(header):
    probe = tomllib.loads(header + "\n__composer_probe__ = true\n")
    names = []
    while isinstance(probe, dict) and "__composer_probe__" not in probe:
        if len(probe) != 1:
            raise ValueError("TOML tableを識別できません")
        key, probe = next(iter(probe.items()))
        names.append(key)
        if isinstance(probe, list):
            probe = probe[-1]
    if not isinstance(probe, dict) or probe.get("__composer_probe__") is not True:
        raise ValueError("TOML tableを識別できません")
    return tuple(names)


def _key(line):
    if line.lstrip().startswith("#") or "=" not in line:
        return None
    # TOMLの引用符つきkey中の '=' は区切りにしない。
    quoted = None
    for at, char in enumerate(line):
        if char in "\"'":
            if quoted == char:
                quoted = None
            elif quoted is None:
                quoted = char
        elif char == "=" and quoted is None:
            try:
                data = tomllib.loads(line[:at].strip() + " = 0\n")
                path = []
                while isinstance(data, dict):
                    if len(data) != 1:
                        return None
                    name, data = next(iter(data.items()))
                    path.append(name)
                return tuple(path)
            except tomllib.TOMLDecodeError:
                return None
    return None


class Document:
    def __init__(self, text):
        self.text = text
        self.data = tomllib.loads(text)
        self.sections = [((), [])]
        multiline = None
        for line in text.splitlines(keepends=True):
            if multiline is None:
                match = HEADER.match(line)
                if match:
                    self.sections.append((_path(match.group(1)), [line]))
                    continue
            self.sections[-1][1].append(line)
            for token in ('"""', "'''"):
                if line.count(token) % 2:
                    if multiline is None:
                        multiline = token
                    elif multiline == token:
                        multiline = None

    def get(self, path):
        value = self.data
        for key in path:
            if not isinstance(value, dict) or key not in value:
                return None, False
            value = value[key]
        return value, True

    def remove_key(self, table, key):
        found = []
        for path, lines in self.sections:
            if path != table:
                continue
            start = 1 if path else 0
            for index in range(len(lines) - 1, start - 1, -1):
                if _key(lines[index]) == (key,):
                    found.append(lines.pop(index))
        if len(found) > 1:
            raise ValueError(f"重複した所有key: {table + (key,)}")
        return found[0] if found else None

    def remove_tree(self, prefix):
        removed, kept = [], []
        for path, lines in self.sections:
            (removed if path[:len(prefix)] == prefix else kept).append((path, lines))
        self.sections = kept
        return "".join("".join(lines) for _, lines in removed)

    def insert_key(self, table, line):
        for path, lines in self.sections:
            if path == table:
                if lines and not lines[-1].endswith("\n"):
                    lines[-1] += "\n"
                lines.append(line)
                return
        if table == ("features",):
            self.sections.append((table, ["\n[features]\n", line]))
            return
        raise ValueError(f"追加先tableがありません: {table}")

    def append(self, snippet):
        if snippet:
            text = self.render().rstrip("\n") + "\n\n" + snippet.lstrip("\n")
            self.__init__(text)

    def render(self):
        return "".join("".join(lines) for _, lines in self.sections)


def policy_owned(data):
    result = {key: data.get(key) for key in TOP}
    result["profiles"] = {key: data.get("permissions", {}).get(key)
                          for key in ("developer", "maintenance", "review")}
    return result


def policy_unowned(data):
    result = copy.deepcopy(data)
    for key in TOP:
        result.pop(key, None)
    profiles = result.get("permissions")
    if isinstance(profiles, dict):
        for name in ("developer", "maintenance", "review"):
            profiles.pop(name, None)
        if not profiles:
            result.pop("permissions", None)
    return result


def policy_fragments(doc):
    fragments = {key: doc.remove_key((), key) for key in TOP}
    fragments["profiles"] = {name: doc.remove_tree(("permissions", name))
                             for name in ("developer", "maintenance", "review")}
    return fragments


def desired_policy(source):
    doc = Document(source)
    if set(doc.data) != set(TOP) | {"permissions"} or set(doc.data["permissions"]) != {"developer", "maintenance", "review"}:
        raise ValueError("権限原本の所有区画が想定と異なります")
    check_source_policy(doc.data["permissions"])
    return policy_owned(doc.data), policy_fragments(doc)


def check_source_policy(profiles):
    """原本自身の退行を止める。通常profileは:read-only基底で、global設定と:workspace_rootsへwriteしない。

    developer/maintenanceのfilesystemは固定allowlistと完全一致させる。maintenanceだけがglobal保守先を追加できる。
    """
    if not all(isinstance(profiles[name], dict) for name in OWNED_PROFILES):
        raise ValueError("権限原本のprofile型が不正です")
    if ([profiles[name].get("extends") for name in OWNED_PROFILES] !=
            [":read-only", ":read-only", ":read-only"]):
        raise ValueError("権限原本の継承がdeveloper/maintenance/reviewとも:read-only基底の兄弟構成と異なります")
    for name, keys in SOURCE_PROFILE_KEYS.items():
        if set(profiles[name]) != keys:
            raise ValueError(f"権限原本の{name}のkeyが固定構成と異なります")
    for name in ("developer", "maintenance"):
        if profiles[name]["network"] != {"enabled": True}:
            raise ValueError(f"権限原本の{name}のnetworkが固定構成と異なります")
    if (profiles["developer"]["filesystem"] != SOURCE_DEVELOPER_FILESYSTEM or
            profiles["maintenance"]["filesystem"] != SOURCE_MAINTENANCE_FILESYSTEM):
        raise ValueError("権限原本のfilesystemが固定allowlistと異なります")
    for name in OWNED_PROFILES:
        profile = profiles[name]
        filesystem = profile.get("filesystem", {})
        if not isinstance(filesystem, dict) or "workspace_roots" in profile:
            raise ValueError(f"権限原本の{name}のfilesystem/workspace_rootsが不正です")
        for base, access in filesystem.items():
            if not isinstance(access, str):
                raise ValueError(f"権限原本の{name}はflat形のaccessだけを使います")
            if access in NON_WRITE_ACCESS:
                continue
            if access != "write" or base == ":workspace_roots":
                raise ValueError(f"権限原本の{name}に不明accessか:workspace_roots writeがあります")
            if name == "review" or (name == "developer" and base not in SOURCE_SPECIAL_WRITE and
                                    _global_write_path(base)):
                raise ValueError(f"権限原本の{name}がglobal設定または判定不能pathへwriteします")


def _known_unmarked_legacy_owned(legacy_source):
    if legacy_source is None or hashlib.sha256(legacy_source.encode()).hexdigest() != KNOWN_UNMARKED_LEGACY_SHA256:
        raise ValueError("markerなし移管の既知旧原本hashが不一致です")
    data = Document(legacy_source).data
    if set(data) != set(TOP) | {"permissions"} or set(data["permissions"]) != {"developer"}:
        raise ValueError("markerなし移管の既知旧原本区画が不正です")
    return policy_owned(data)


def _old_marker(text):
    starts, ends = text.count(LEGACY_START), text.count(LEGACY_END)
    if starts != ends or starts not in (0, 2):
        raise ValueError("旧wealth markerが不正です")
    return text.replace(LEGACY_START, "").replace(LEGACY_END, ""), bool(starts)


OWNED_PROFILES = ("developer", "maintenance", "review")
# 公式accessはread/write/deny。denyは非write、noneなど他の値は不明として拒否する。
NON_WRITE_ACCESS = ("read", "deny")
# 原本developerだけに許す実行時の一時領域。未知profileの判定では従来どおり特殊baseとして拒否する。
SOURCE_SPECIAL_WRITE = (":tmpdir", ":slash_tmp")
# 原本の固定allowlist。広げる変更はcomposer実行時に拒否し、原本と同時にここを変える必要がある。
# .codexは次回起動時の権限を決めるため、developerは配下を拒否し、maintenanceだけが明示writeする。
# CLI 0.155.1では/**/.codex/** denyが同profileの正確path例外より優先されたため、maintenanceは継承しない兄弟profile。
SOURCE_DEVELOPER_FILESYSTEM = {
    "~/Workspace/agent-crew": "write",
    "~/Workspace/agent-crew/.git": "write",
    "~/Workspace/agent-crew/.codex": "read",
    "~/Workspace/agent-crew/.codex/config.toml": "read",
    # worktree等の既存・新規の入れ子.codexもtrust済みproject設定として読まれるため配下を拒否する。
    "/**/.codex/**": "deny",
    "~/.cache": "write", "~/.npm": "write", "~/.local/share/uv": "write", "~/Library/Caches": "write",
    ":tmpdir": "write", ":slash_tmp": "write",
}
SOURCE_MAINTENANCE_FILESYSTEM = {path: "write" for path in (
    "~/Workspace/agent-crew", "~/Workspace/agent-crew/.git", "~/Workspace/agent-crew/.codex",
    "~/.cache", "~/.npm", "~/.local/share/uv", "~/Library/Caches", ":tmpdir", ":slash_tmp",
    "~/.codex/config.toml", "~/.codex/config-composer", "~/.codex/AGENTS.md", "~/.codex/rules",
    "~/.codex/skills", "~/.codex/agents", "~/.agents/skills", "~/.claude/settings.json",
    "~/.claude/skills", "~/.claude/agents")}
SOURCE_PROFILE_KEYS = {"developer": {"description", "extends", "filesystem", "network"},
                       "maintenance": {"description", "extends", "filesystem", "network"},
                       "review": {"description", "extends"}}


def _global_write_path(path):
    """homeのCodex設定領域、その祖先・子孫、等価な絶対/~/symlink/大文字小文字違い/交差しうるglobを検出。

    基準が実行時まで決まらない相対path、環境変数展開の余地がある`$`、解決できないpathも拒否側。
    """
    if not isinstance(path, str):
        return True
    if path == ":root":
        return True
    if path.startswith(":") or "$" in path:
        # 呼出し側で:rootを展開済み。それ以外の特殊pathと環境変数展開の余地は判定できない。
        return True
    try:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            return True  # cwdやworkspace rootのどれが基準か不明
        resolved = candidate.resolve(strict=False)
    except (RuntimeError, OSError, ValueError):
        return True  # symlink loop、~user展開失敗、NUL等
    # macOS標準volumeは大文字小文字を区別しないため、全OSでcasefoldして安全側に比較する。
    parts = [part.casefold() for part in resolved.parts]
    protected = [part.casefold() for part in (Path.home() / ".codex").resolve(strict=False).parts]
    # protected rootと先頭部品が一致し続ければ、同一・祖先・子孫のいずれか。
    # `*`と`{a,b}`は`/`を跨ぐ実装もありうるため、その部品は`*`/`{`より前のliteralが
    # protected部品の先頭と矛盾しない限り交差とみなす。1文字だけの`?`/`[]`は同じ深さで照合する。
    for index, part in enumerate(parts):
        if index >= len(protected):
            return True
        spanning = [part.find(char) for char in "*{" if char in part]
        if spanning:
            return protected[index].startswith(part[:min(spanning)])
        if any(char in part for char in "?["):
            if not fnmatch.fnmatchcase(protected[index], part):
                return False
        elif part != protected[index]:
            return False
    return True


def _profile_chain(name, profiles):
    """extendsを辿った(filesystem群, :workspace継承有無)。判定不能ならNone。"""
    filesystems, seen = [], set()
    current = name
    while True:
        if current in seen or not isinstance(profiles.get(current), dict):
            return None  # 循環、不明親、型不正
        seen.add(current)
        profile = profiles[current]
        filesystem = profile.get("filesystem", {})
        if not isinstance(filesystem, dict):
            return None
        if "workspace_roots" in profile and not isinstance(profile["workspace_roots"], dict):
            return None
        filesystems.append(filesystem)
        parent = profile.get("extends")
        if parent == ":read-only":
            return filesystems, False
        if parent == ":workspace":
            return filesystems, True
        if not isinstance(parent, str) or parent.startswith(":"):
            # extendsなしは公式記述では制限基底だが、CLI 0.155.1のcanaryで選択時にabortし確認できない。
            return None  # extendsなし、未知の組込親、型不正は拒否する
        current = parent


def _unknown_profile_global_write(name, profiles):
    """未知profileの実効writeが~/.codex領域へ届かないと証明できなければTrue（拒否）。

    公式Permissionsでは:workspace_rootsはprofile指定rootに加え実行時workspace rootにも適用され、
    実行時rootは移行時点で未知（~/.codex自身や~もありうる）。そのため:workspace継承と
    :workspace_rootsへのwriteは、明示rootの有無や組込保護の推測によらず拒否する。
    """
    chain = _profile_chain(name, profiles)
    if chain is None:
        return True
    filesystems, workspace = chain
    if workspace:
        return True
    for filesystem in filesystems:
        for base, access in filesystem.items():
            if isinstance(access, str):
                if access in NON_WRITE_ACCESS:
                    continue
                if access != "write" or base == ":workspace_roots":
                    return True
                if _global_write_path(base):
                    return True
                continue
            if not isinstance(access, dict):
                return True
            for subpath, permission in access.items():
                if not isinstance(subpath, str) or not isinstance(permission, str):
                    return True
                if permission in NON_WRITE_ACCESS:
                    continue
                if permission != "write" or base == ":workspace_roots":
                    return True
                if base == ":root":
                    dangerous = _global_write_path("/" + subpath)
                elif base.startswith(":"):
                    dangerous = True  # 判定不能な特殊base
                else:
                    # 相対baseは基準不明のため、subpathとの結合結果によらず拒否する。
                    try:
                        absolute = Path(base).expanduser().is_absolute()
                    except RuntimeError:
                        absolute = False
                    dangerous = not absolute or _global_write_path(str(Path(base) / subpath))
                if dangerous:
                    return True
    return False


def check_policy_conflicts(doc, expected, legacy, after_profiles=None):
    if any(key in doc.data for key in ("sandbox_mode", "sandbox_workspace_write")):
        raise ValueError("legacy sandbox設定がnamed permissionsを上書きします")
    for name, profile in doc.data.get("profiles", {}).items():
        if isinstance(profile, dict) and "sandbox_mode" in profile:
            raise ValueError(f"profile {name} のlegacy sandbox設定を先に整理してください")
    permissions = doc.data.get("permissions", {})
    if not isinstance(permissions, dict):
        raise ValueError("permissionsの型を判定できません")
    unknown = {name: profile for name, profile in permissions.items() if name not in OWNED_PROFILES}
    # 未知profileが所有profileをextendsする場合、合成前の現値と合成後の原本のどちらでも評価する。
    views = [permissions]
    if after_profiles is not None:
        views.append({**unknown, **{name: value for name, value in after_profiles.items() if value is not None}})
    for name in unknown:
        if any(_unknown_profile_global_write(name, view) for view in views):
            raise ValueError(f"未知profile {name} にglobal write権限があります")
    if expected is not None:
        if policy_owned(doc.data) != expected:
            raise ValueError("所有権限区画に独自変更があります")
    elif legacy is not None:
        current = policy_owned(doc.data)
        if any(current[key] != legacy[key] for key in TOP) or current["profiles"]["developer"] != legacy["profiles"]["developer"]:
            raise ValueError("旧wealth所有区画が原本と一致しません")
        if current["profiles"]["maintenance"] is not None or current["profiles"]["review"] is not None:
            raise ValueError("新profileが台帳なしで存在します")
    else:
        if any(doc.get((key,))[1] for key in TOP) or any(doc.get(("permissions", name))[1]
                                                            for name in ("developer", "maintenance", "review")):
            raise ValueError("台帳なしの所有権限区画があります")


def compose_policy(text, source, expected=None, legacy_source=None, legacy_unmarked=False):
    clean, marked = _old_marker(text)
    if legacy_unmarked and (marked or expected is not None):
        raise ValueError("markerなし既知旧設定の初回移管条件に一致しません")
    doc = Document(clean)
    if legacy_unmarked:
        legacy = _known_unmarked_legacy_owned(legacy_source)
    else:
        legacy = policy_owned(Document(legacy_source).data) if marked and legacy_source else None
    if (marked or legacy_unmarked) and legacy is None:
        raise ValueError("旧wealth markerの原本照合ができません")
    check_policy_conflicts(doc, expected, legacy, desired_policy(source)[0]["profiles"])
    before = policy_owned(doc.data)
    old_fragments = policy_fragments(doc)
    old_fragments["legacy_marked"] = marked
    old_fragments["legacy_unmarked"] = legacy_unmarked
    desired, fragments = desired_policy(source)
    if expected is not None and before == desired:
        return text, before, desired, old_fragments
    for key in TOP:
        doc.insert_key((), fragments[key])
    doc.append("".join(fragments["profiles"].values()))
    result = doc.render()
    if policy_owned(Document(result).data) != desired:
        raise ValueError("合成後の権限区画が原本と不一致")
    if policy_unowned(Document(clean).data) != policy_unowned(Document(result).data):
        raise ValueError("所有外のTOML意味木が変化しました。合成を拒否します")
    return result, before, desired, old_fragments


def hook_owned(data, keys):
    hooks = data.get("hooks", {})
    state = hooks.get("state", {}) if isinstance(hooks, dict) else {}
    return {"notify": data.get("notify"),
            "features.hooks": data.get("features", {}).get("hooks"),
            "entries": {key: state.get(key) for key in keys}}


def hook_unowned(data, keys):
    result = copy.deepcopy(data)
    result.pop("notify", None)
    features = result.get("features")
    if isinstance(features, dict):
        features.pop("hooks", None)
        if not features:
            result.pop("features", None)
    hooks = result.get("hooks")
    if isinstance(hooks, dict):
        state = hooks.get("state")
        if isinstance(state, dict):
            for key in keys:
                state.pop(key, None)
            if not state:
                hooks.pop("state", None)
        if not hooks:
            result.pop("hooks", None)
    return result


def compose_hooks(text, states, expected=None, previous_keys=()):
    """hook区画だけを更新し、他のtable/配列/引用符keyを保つ。"""
    doc = Document(text)
    keys = sorted({item["key"] for item in states})
    if len(keys) != len(states):
        raise ValueError("hook state keyが重複しています")
    all_keys = sorted(set(keys) | set(previous_keys))
    if expected is not None:
        if hook_owned(doc.data, sorted(expected["entries"])) != expected:
            raise ValueError("所有hook区画に独自変更があります")
        for key in set(keys) - set(previous_keys):
            if doc.get(("hooks", "state", key))[1]:
                raise ValueError("新hook keyが既存設定と競合します")
    else:
        current = hook_owned(doc.data, all_keys)
        if current["notify"] is not None or current["features.hooks"] is not None or any(
                value is not None for value in current["entries"].values()):
            raise ValueError("台帳なしのhook所有区画があります")
    before = hook_owned(doc.data, all_keys)
    fragments = {"notify": doc.remove_key((), "notify"),
                 "features.hooks": doc.remove_key(("features",), "hooks"),
                 "entries": {key: doc.remove_tree(("hooks", "state", key)) for key in all_keys}}
    doc.insert_key((), "notify = []\n")
    doc.insert_key(("features",), "hooks = true\n")
    tables = []
    for item in sorted(states, key=lambda entry: entry["key"]):
        tables.append("[hooks.state." + json.dumps(item["key"], ensure_ascii=False) + "]\n")
        tables.append("enabled = " + str(item["enabled"]).lower() + "\n")
        if item["enabled"]:
            tables.append("trusted_hash = " + json.dumps(item["trusted_hash"]) + "\n")
        tables.append("\n")
    doc.append("".join(tables))
    result = doc.render()
    after = hook_owned(Document(result).data, all_keys)
    if after["notify"] != [] or after["features.hooks"] is not True:
        raise ValueError("hook合成後の値が不正です")
    if hook_unowned(Document(text).data, all_keys) != hook_unowned(Document(result).data, all_keys):
        raise ValueError("所有外のTOML意味木が変化しました。hook合成を拒否します")
    return result, before, after, fragments


def verify_hook_section(text, expected):
    current = hook_owned(Document(text).data, sorted(expected["entries"]))
    if current != expected:
        raise ValueError("所有hook区画に独自変更があります")


def restore_policy(text, expected, fragments):
    doc = Document(text)
    if policy_owned(doc.data) != expected:
        raise ValueError("rollback対象の権限区画が適用後と一致しません")
    policy_fragments(doc)
    top_text = "".join(fragments[key] or "" for key in TOP)
    profiles_text = "".join(fragments["profiles"].values())
    if fragments.get("legacy_marked"):
        top_text = LEGACY_START + top_text + LEGACY_END
        profiles_text = LEGACY_START + profiles_text + LEGACY_END
    if top_text:
        doc.insert_key((), top_text)
    doc.append(profiles_text)
    result = doc.render()
    if policy_unowned(Document(text).data) != policy_unowned(Document(result).data):
        raise ValueError("rollbackで所有外のTOML意味木が変化します")
    return result


def restore_hooks(text, expected, fragments):
    verify_hook_section(text, expected)
    doc = Document(text)
    doc.remove_key((), "notify")
    doc.remove_key(("features",), "hooks")
    for key in expected["entries"]:
        doc.remove_tree(("hooks", "state", key))
    if fragments["notify"] is not None:
        doc.insert_key((), fragments["notify"])
    if fragments["features.hooks"] is not None:
        doc.insert_key(("features",), fragments["features.hooks"])
    doc.append("".join(fragments["entries"].values()))
    result = doc.render()
    if hook_unowned(Document(text).data, expected["entries"]) != hook_unowned(Document(result).data, expected["entries"]):
        raise ValueError("hook rollbackで所有外のTOML意味木が変化します")
    return result


@contextmanager
def lock(state_dir):
    _reject_symlink(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    _reject_symlink(state_dir)
    os.chmod(state_dir, 0o700)
    descriptor = os.open(state_dir / "composer.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _policy_temp_dir(target, state_dir):
    """globalだけ固定private台帳内で一時ファイルを作る。lock前に検証する。"""
    _reject_symlink(target)
    _reject_symlink(state_dir)
    global_target = (Path.home() / ".codex/config.toml").resolve()
    if target.resolve() == global_target:
        fixed_state = Path.home() / ".codex/config-composer"
        _reject_symlink(fixed_state)
        if state_dir.resolve() != fixed_state.resolve():
            raise ValueError("global設定のprivate台帳は~/.codex/config-composer固定です")
        return state_dir
    return target.parent


def _check_temp_device(path, temp_dir):
    _reject_symlink(temp_dir)
    if temp_dir.stat().st_dev != path.parent.stat().st_dev:
        raise ValueError("一時ファイルと設定対象のfilesystemが異なるためatomic置換できません")


def _precheck_private_temp_device(path, temp_dir):
    # repoの親directoryは初回atomic_writeで作る。別dirを使うglobalだけ事前検査する。
    if temp_dir != path.parent:
        _check_temp_device(path, temp_dir)


def atomic_write(path, content, expected, temp_dir=None):
    temp_dir = temp_dir or path.parent
    _reject_symlink(path)
    current = path.read_bytes() if path.exists() else None
    if current != expected:
        raise ValueError("直前hash照合で外部編集を検出しました")
    path.parent.mkdir(parents=True, exist_ok=True)
    _check_temp_device(path, temp_dir)
    fd, name = tempfile.mkstemp(prefix=".codex-compose-", dir=temp_dir)
    primary = None
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, path.stat().st_mode & 0o777 if path.exists() else 0o600)
        _reject_symlink(path)
        if (path.read_bytes() if path.exists() else None) != expected:
            raise ValueError("置換直前に外部編集を検出しました")
        os.replace(name, path)
    except BaseException as error:
        primary = error
        raise
    finally:
        if os.path.exists(name):
            try:
                os.unlink(name)
            except OSError as cleanup_error:
                if primary is None:
                    raise
                primary.add_note(f"一時ファイルのcleanupも失敗: {cleanup_error}")


def atomic_remove(path, expected):
    _reject_symlink(path)
    if (path.read_bytes() if path.exists() else None) != expected:
        raise ValueError("削除直前のhash照合で外部編集を検出しました")
    path.unlink(missing_ok=True)


def _reject_symlink(path):
    if path.is_symlink():
        raise ValueError("symlink設定は台帳と置換先がずれるため拒否します")


def _ledger_path(state_dir, target):
    _reject_symlink(target)
    return state_dir / (hashlib.sha256(str(target.resolve()).encode()).hexdigest() + ".json")


def _read_ledger(path):
    if not path.exists():
        return None
    record = json.loads(path.read_text())
    if record.get("status") != "applied":
        raise ValueError("前回適用が途中です。private台帳と対象を確認して復旧してください")
    return record


def _expected_hex(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"markerなし移管の{label}をSHA-256の64文字で明示してください")
    return value


def _verify_unmarked_record(record, target):
    kind = record.get("migration_kind")
    if kind is None:
        return False
    if kind != "legacy_unmarked":
        raise ValueError("不明な移管種別の台帳です")
    if record.get("expected_target_path") != str(target.resolve()):
        raise ValueError("markerなし移管台帳の対象pathが不一致です")
    if record.get("expected_legacy_sha256") != KNOWN_UNMARKED_LEGACY_SHA256:
        raise ValueError("markerなし移管台帳の旧原本hashが不一致です")
    if (record.get("before_fragments", {}).get("legacy_unmarked") is not True or
            record["before_fragments"].get("legacy_marked") is not False):
        raise ValueError("markerなし移管台帳の独立フラグが不一致です")
    legacy = record["legacy_source"]
    if _known_unmarked_legacy_owned(legacy) != record["before"]:
        raise ValueError("markerなし移管台帳のbefore区画が旧原本と不一致です")
    if hashlib.sha256(record["source"].encode()).hexdigest() != record.get("expected_source_sha256"):
        raise ValueError("markerなし移管台帳の新原本hashが不一致です")
    desired = desired_policy(record["source"])[0]
    if (desired != record["after"] or
            hashlib.sha256(canonical(desired)).hexdigest() != record.get("expected_after_owned_sha256")):
        raise ValueError("markerなし移管台帳のafter区画が不一致です")
    backup = Path(record["backup"]) / "config.toml"
    if (not backup.is_file() or
            hashlib.sha256(backup.read_bytes()).hexdigest() != record.get("expected_target_sha256") or
            record.get("before_hash") != sha(backup.read_bytes())):
        raise ValueError("markerなし移管台帳のprivate backupが不一致です")
    return True


def recover_policy(target, state_dir):
    temp_dir = _policy_temp_dir(target, state_dir)
    with lock(state_dir):
        _precheck_private_temp_device(target, temp_dir)
        path = _ledger_path(state_dir, target)
        record = json.loads(path.read_text())
        legacy_unmarked = _verify_unmarked_record(record, target)
        original = target.read_bytes() if target.exists() else None
        current = (original or b"").decode()
        owned = policy_owned(Document(current).data)
        if record["status"] == "rollback_pending":
            if legacy_unmarked:
                raise ValueError("markerなし初回世代rollbackは禁止。pendingの前進復旧だけを許可します")
            if owned == record["before"]:
                prior = Path(record["backup"]) / "ledger.json"
                if prior.exists():
                    atomic_write(path, prior.read_bytes(), path.read_bytes())
                else:
                    atomic_remove(path, path.read_bytes())
                return "rolled_back"
            if owned == record["after"]:
                record["status"] = "applied"
                atomic_write(path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode(), path.read_bytes())
                return "rollback_not_applied"
            raise ValueError("rollback途中の所有区画がbefore/afterと不一致です")
        if record["status"] != "pending":
            raise ValueError("復旧対象のpending世代がありません")
        if owned == record["after"]:
            record["status"] = "applied"
            atomic_write(path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode(), path.read_bytes())
            return "applied"
        if owned == record["before"]:
            if record["before_fragments"].get("legacy_marked") or legacy_unmarked:
                content, _, after, _ = compose_policy(current, record["source"],
                                                       legacy_source=record["legacy_source"],
                                                       legacy_unmarked=legacy_unmarked)
                if after != record["after"]:
                    raise ValueError("復旧原本の所有区画が予定世代と不一致です")
                atomic_write(target, content.encode(), original, temp_dir)
                record["status"] = "applied"
                atomic_write(path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode(), path.read_bytes())
                return "applied_from_legacy"
            prior = Path(record["backup"]) / "ledger.json"
            if prior.exists():
                atomic_write(path, prior.read_bytes(), path.read_bytes())
            else:
                atomic_remove(path, path.read_bytes())
            return "not_applied"
        raise ValueError("所有区画がbefore/afterのいずれとも不一致。手動確認が必要です")


def rollback_policy(target, state_dir):
    temp_dir = _policy_temp_dir(target, state_dir)
    with lock(state_dir):
        _precheck_private_temp_device(target, temp_dir)
        path = _ledger_path(state_dir, target)
        record = _read_ledger(path)
        if record is None:
            raise ValueError("rollback対象の台帳がありません")
        _verify_unmarked_record(record, target)
        if (record["before_fragments"].get("legacy_marked") or record["before_fragments"].get("legacy_unmarked") or
                record.get("migration_kind") == "legacy_unmarked"):
            raise ValueError("旧wealth広権限を復活させる初回世代rollbackは禁止。安全復旧は--recoverで新世代へ進めてください")
        original = target.read_bytes() if target.exists() else None
        restored = restore_policy((original or b"").decode(), record["after"], record["before_fragments"])
        prior = Path(record["backup"]) / "ledger.json"
        record["status"] = "rollback_pending"
        atomic_write(path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode(), path.read_bytes())
        if record["before_existed"] or policy_unowned(Document(restored).data) or restored.strip():
            atomic_write(target, restored.encode(), original, temp_dir)
        else:
            atomic_remove(target, original)
        if prior.exists():
            atomic_write(path, prior.read_bytes(), path.read_bytes())
        else:
            atomic_remove(path, path.read_bytes())
        return {"target": str(target), "restored_hash": sha(restored.encode())}


def apply_policy(target, source, legacy_source, state_dir, write=False, *, adopt_unmarked=False,
                 expected_target_path=None, expected_target_sha256=None, expected_source_sha256=None,
                 expected_legacy_sha256=None, expected_after_owned_sha256=None):
    expected_values = (expected_target_path, expected_target_sha256, expected_source_sha256,
                       expected_legacy_sha256, expected_after_owned_sha256)
    if adopt_unmarked:
        # write=Falseはlock・台帳・backupを作らない同一照合のpreview。書込みは下の`write and changed`だけ。
        if target.resolve() != (Path.home() / ".codex/config.toml").resolve():
            raise ValueError("markerなし移管はglobal設定だけが対象です")
        if expected_target_path != str(target.resolve()):
            raise ValueError("markerなし移管の対象pathが不一致です")
        for label, value in zip(("target", "source", "legacy", "after区画"), expected_values[1:]):
            _expected_hex(value, label)
    elif any(value is not None for value in expected_values):
        raise ValueError("expected hashはmarkerなし移管の明示opt-in専用です")
    desired_policy(source)  # 退行した原本はlock・台帳を作る前に拒否する
    temp_dir = _policy_temp_dir(target, state_dir)
    with lock(state_dir) if write else nullcontext():
        if write:
            _precheck_private_temp_device(target, temp_dir)
        ledger_path = _ledger_path(state_dir, target)
        if adopt_unmarked and (ledger_path.exists() or ledger_path.is_symlink()):
            raise ValueError("markerなし初回移管は既存ledger/pendingを拒否します")
        ledger = None if adopt_unmarked else _read_ledger(ledger_path)
        original = target.read_bytes() if target.exists() else None
        if adopt_unmarked:
            if (original is None or hashlib.sha256(original).hexdigest() != expected_target_sha256 or
                    hashlib.sha256(source.encode()).hexdigest() != expected_source_sha256 or
                    hashlib.sha256(legacy_source.encode()).hexdigest() != expected_legacy_sha256 or
                    expected_legacy_sha256 != KNOWN_UNMARKED_LEGACY_SHA256):
                raise ValueError("markerなし移管のtarget/source/legacy固定hashが不一致です")
        text = original.decode() if original is not None else ""
        expected = ledger["after"] if ledger else None
        new, before, after, fragments = compose_policy(text, source, expected, legacy_source,
                                                        legacy_unmarked=adopt_unmarked)
        if (adopt_unmarked and
                hashlib.sha256(canonical(after)).hexdigest() != expected_after_owned_sha256):
            raise ValueError("markerなし移管の合成後区画hashが不一致です")
        changed = new != text
        generation = ledger["generation"] + 1 if ledger and changed else (ledger["generation"] if ledger else 1)
        result = {"target": str(target), "changed": changed, "before_hash": sha(original or b""),
                  "after_hash": sha(new.encode()), "generation": generation}
        if adopt_unmarked:
            # 本文を出さずに、所有外意味木の保持と合成後区画を照合できる値だけ返す。
            result.update({"applied": bool(write and changed),
                           "after_owned_sha256": hashlib.sha256(canonical(after)).hexdigest(),
                           "unowned_sha256": hashlib.sha256(
                               canonical(policy_unowned(Document(new).data))).hexdigest()})
        if write and changed:
            backup_dir = state_dir / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup_dir.mkdir(parents=True, mode=0o700)
            if original is not None:
                (backup_dir / "config.toml").write_bytes(original)
                os.chmod(backup_dir / "config.toml", 0o600)
            if ledger_path.exists():
                (backup_dir / "ledger.json").write_bytes(ledger_path.read_bytes())
                os.chmod(backup_dir / "ledger.json", 0o600)
            record = {**result, "status": "pending", "before": before, "after": after,
                      "before_fragments": fragments, "before_existed": original is not None,
                      "backup": str(backup_dir), "generation": result["generation"],
                      "source": source, "legacy_source": legacy_source}
            if adopt_unmarked:
                record.update({"migration_kind": "legacy_unmarked",
                               "expected_target_path": expected_target_path,
                               "expected_target_sha256": expected_target_sha256,
                               "expected_source_sha256": expected_source_sha256,
                               "expected_legacy_sha256": expected_legacy_sha256,
                               "expected_after_owned_sha256": expected_after_owned_sha256})
            atomic_write(ledger_path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode(),
                         ledger_path.read_bytes() if ledger_path.exists() else None)
            atomic_write(target, new.encode(), original, temp_dir)
            record["status"] = "applied"
            atomic_write(ledger_path, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode(), ledger_path.read_bytes())
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path.home() / ".codex/config.toml")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".codex/config-composer")
    parser.add_argument("--source", type=Path, default=ROOT / "config/codex/permissions.toml")
    parser.add_argument("--legacy-source", type=Path, default=ROOT / "config/codex/legacy-developer.toml")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--adopt-legacy-unmarked", action="store_true")
    parser.add_argument("--expected-target-path")
    parser.add_argument("--expected-target-sha256")
    parser.add_argument("--expected-source-sha256")
    parser.add_argument("--expected-legacy-sha256")
    parser.add_argument("--expected-after-owned-sha256")
    args = parser.parse_args(argv)
    try:
        if sum((args.apply, args.recover, args.rollback)) > 1:
            raise ValueError("--apply/--recover/--rollbackは排他です")
        if args.adopt_legacy_unmarked and (args.recover or args.rollback):
            raise ValueError("--adopt-legacy-unmarkedはpreviewか--applyだけに使えます")
        if (args.recover or args.rollback) and any((args.expected_target_path, args.expected_target_sha256,
                args.expected_source_sha256, args.expected_legacy_sha256, args.expected_after_owned_sha256)):
            raise ValueError("expected hashは--applyのmarkerなし移管専用です")
        if args.recover:
            result = {"recovered": recover_policy(args.target, args.state_dir)}
        elif args.rollback:
            result = rollback_policy(args.target, args.state_dir)
        else:
            result = apply_policy(args.target, args.source.read_text(), args.legacy_source.read_text(),
                                  args.state_dir, args.apply, adopt_unmarked=args.adopt_legacy_unmarked,
                                  expected_target_path=args.expected_target_path,
                                  expected_target_sha256=args.expected_target_sha256,
                                  expected_source_sha256=args.expected_source_sha256,
                                  expected_legacy_sha256=args.expected_legacy_sha256,
                                  expected_after_owned_sha256=args.expected_after_owned_sha256)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, tomllib.TOMLDecodeError) as error:
        print(f"composer停止: {error}")
        for note in getattr(error, "__notes__", ()):
            print(f"composer補足: {note}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
