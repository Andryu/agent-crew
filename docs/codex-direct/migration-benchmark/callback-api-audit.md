# 固定CPython 3.12.13 callback監査表

run.pyの既知call集合・Path method・hash methodを抽出し、全89 APIのcallback有無を記録する。`callback-api-inventory.json`に署名parameter、実装/doc hash、callback位置（0-origin）を固定。C builtinでsignatureが取得できない場合はnullを明示し、同版CPythonソースとdocを照合した。再生成だけで監査済みとは扱わない。

位置/keyword probeはprint/openを使い、単なる別理由のunknownではなくcallback検査理由を必須とする。callable default・sourceの引数直接call・callback語彙も独立に照合する。API追加・署名/source変更時に手動再監査が必要。暗黙protocolは別のAST/import subset検査対象。

| API | callback（位置 / keyword） | 実装根拠 |
|---|---|---|
| `Path` | なし | Lib/pathlib.py |
| `Path.cwd` | なし | Lib/pathlib.py |
| `all` | なし | Python/bltinmodule.c |
| `any` | なし | Python/bltinmodule.c |
| `builtins.open` | opener=7 | Modules/_io/_iomodule.c |
| `bytes` | なし | Objects/bytesobject.c |
| `dict` | なし | Objects/dictobject.c |
| `enumerate` | なし | Objects/enumobject.c |
| `hasattr` | なし | Python/bltinmodule.c |
| `hashlib.HASH.digest` | なし | Modules/_hashopenssl.c |
| `hashlib.HASH.hexdigest` | なし | Modules/_hashopenssl.c |
| `hashlib.sha256` | なし | Modules/_hashopenssl.c |
| `int` | なし | Objects/longobject.c |
| `isinstance` | なし | Python/bltinmodule.c |
| `json.dumps` | cls=None, default=None | Lib/json/__init__.py + decoder.py + encoder.py |
| `json.loads` | cls=None, object_hook=None, parse_float=None, parse_int=None, parse_constant=None, object_pairs_hook=None | Lib/json/__init__.py + decoder.py + encoder.py |
| `len` | なし | Python/bltinmodule.c |
| `list` | なし | Objects/listobject.c |
| `max` | key=None | Python/bltinmodule.c |
| `min` | key=None | Python/bltinmodule.c |
| `open` | opener=7 | Modules/_io/_iomodule.c |
| `os.access` | なし | Modules/posixmodule.c |
| `os.chdir` | なし | Modules/posixmodule.c |
| `os.getcwd` | なし | Modules/posixmodule.c |
| `os.getpid` | なし | Modules/posixmodule.c |
| `os.getuid` | なし | Modules/posixmodule.c |
| `os.link` | なし | Modules/posixmodule.c |
| `os.listdir` | なし | Modules/posixmodule.c |
| `os.lstat` | なし | Modules/posixmodule.c |
| `os.makedirs` | なし | Lib/os.py |
| `os.mkdir` | なし | Modules/posixmodule.c |
| `os.open` | なし | Modules/posixmodule.c |
| `os.path.basename` | なし | Lib/posixpath.py + genericpath.py |
| `os.path.commonpath` | なし | Lib/posixpath.py + genericpath.py |
| `os.path.dirname` | なし | Lib/posixpath.py + genericpath.py |
| `os.path.exists` | なし | Lib/posixpath.py + genericpath.py |
| `os.path.isdir` | なし | Lib/posixpath.py + genericpath.py |
| `os.path.isfile` | なし | Lib/posixpath.py + genericpath.py |
| `os.path.join` | なし | Lib/posixpath.py + genericpath.py |
| `os.path.normpath` | なし | Lib/posixpath.py + genericpath.py |
| `os.path.realpath` | なし | Lib/posixpath.py + genericpath.py |
| `os.path.relpath` | なし | Lib/posixpath.py + genericpath.py |
| `os.path.split` | なし | Lib/posixpath.py + genericpath.py |
| `os.readlink` | なし | Modules/posixmodule.c |
| `os.remove` | なし | Modules/posixmodule.c |
| `os.rename` | なし | Modules/posixmodule.c |
| `os.replace` | なし | Modules/posixmodule.c |
| `os.scandir` | なし | Modules/posixmodule.c |
| `os.stat` | なし | Modules/posixmodule.c |
| `os.symlink` | なし | Modules/posixmodule.c |
| `os.unlink` | なし | Modules/posixmodule.c |
| `os.walk` | onerror=2 | Lib/os.py |
| `pathlib.Path` | なし | Lib/pathlib.py |
| `pathlib.Path.cwd` | なし | Lib/pathlib.py |
| `pathlib.Path.exists` | なし | Lib/pathlib.py |
| `pathlib.Path.glob` | なし | Lib/pathlib.py |
| `pathlib.Path.hardlink_to` | なし | Lib/pathlib.py |
| `pathlib.Path.is_dir` | なし | Lib/pathlib.py |
| `pathlib.Path.is_file` | なし | Lib/pathlib.py |
| `pathlib.Path.iterdir` | なし | Lib/pathlib.py |
| `pathlib.Path.link_to` | runtimeに存在せず | Lib/pathlib.py |
| `pathlib.Path.lstat` | なし | Lib/pathlib.py |
| `pathlib.Path.mkdir` | なし | Lib/pathlib.py |
| `pathlib.Path.open` | なし | Lib/pathlib.py |
| `pathlib.Path.read_bytes` | なし | Lib/pathlib.py |
| `pathlib.Path.read_text` | なし | Lib/pathlib.py |
| `pathlib.Path.rename` | なし | Lib/pathlib.py |
| `pathlib.Path.replace` | なし | Lib/pathlib.py |
| `pathlib.Path.rglob` | なし | Lib/pathlib.py |
| `pathlib.Path.stat` | なし | Lib/pathlib.py |
| `pathlib.Path.symlink_to` | なし | Lib/pathlib.py |
| `pathlib.Path.unlink` | なし | Lib/pathlib.py |
| `pathlib.Path.write_bytes` | なし | Lib/pathlib.py |
| `pathlib.Path.write_text` | なし | Lib/pathlib.py |
| `print` | なし | Python/bltinmodule.c |
| `range` | なし | Objects/rangeobject.c |
| `runpy.run_path` | なし | Lib/runpy.py (import禁止の防御表) |
| `set` | なし | Objects/setobject.c |
| `shutil.copy` | なし | Lib/shutil.py |
| `shutil.copy2` | なし | Lib/shutil.py |
| `shutil.copyfile` | なし | Lib/shutil.py |
| `shutil.copytree` | ignore=3, copy_function=4 | Lib/shutil.py |
| `shutil.move` | copy_function=2 | Lib/shutil.py |
| `shutil.rmtree` | onerror=2, onexc=None | Lib/shutil.py |
| `sorted` | key=None | Python/bltinmodule.c |
| `str` | なし | Objects/unicodeobject.c |
| `sum` | なし | Python/bltinmodule.c |
| `tuple` | なし | Objects/tupleobject.c |
| `zip` | なし | Python/bltinmodule.c |

min/maxはkeyがkeyword-only、defaultはdata。Path.openはbuiltin openと異なりopener引数を持たない。shutil.move/copytreeの省略時copy2はstdlib既定値として保持するが、明示callable（copy2/print/open/int等）は純粋性を証明せずunknown。Noneは既存方針どおり許可する（実API成功の保証ではなく、callback実行能力がないという分類）。False等の非None値もcallback位置では保守的にunknown。

C実装根拠: [CPython v3.12.13](https://github.com/python/cpython/tree/v3.12.13)。取得した13 sourceのhashをJSON表へ記録。stdlib Python sourceは固定runtimeから照合。
