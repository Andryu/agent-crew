"""固定runtimeのAPI棚卸し。未知API/署名/source変更は再監査を要求する。"""
import ast
import builtins
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sys
import textwrap

HERE = Path(__file__).resolve().parent
TABLES = {'path_api', 'path_methods', 'known_names', 'safe_module_calls',
          'callback_slots', 'callback_keywords', 'method_slots'}


def classifier_tables():
    tree = ast.parse((HERE / 'run.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == '_fixed_python_code_attempts')
    result = {}
    for node in function.body:
        if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in TABLES):
            # repoの定数表だけを評価する。分類対象のPythonは実行しない。
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<tables>', 'exec'),
                 {'__builtins__': {}}, result)
    assert set(result) == TABLES
    return result


def api_names(tables):
    return (set(tables['path_api']) | tables['safe_module_calls'] | tables['known_names']
            | {'pathlib.Path.' + n for n in tables['path_methods']}
            | {'hashlib.HASH.digest', 'hashlib.HASH.hexdigest'})


def api_object(name):
    if name.startswith('hashlib.HASH.'):
        import hashlib
        return getattr(type(hashlib.sha256()), name.rsplit('.', 1)[1])
    if name == 'Path':
        return Path
    if name.startswith('Path.'):
        return getattr(Path, name.split('.')[1])
    parts = name.split('.')
    obj = getattr(builtins, name, None) if len(parts) == 1 else importlib.import_module(parts[0])
    for part in parts[1:]:
        obj = getattr(obj, part, None)
    return obj


def api_source(obj):
    try:
        return textwrap.dedent(inspect.getsource(obj))
    except (OSError, TypeError):
        # frozen os/posixpath/genericpath/runpyにも同梱stdlib sourceを照合する。
        if inspect.isfunction(obj):
            module = importlib.import_module(obj.__module__)
            path = Path(module.__file__)
            text = path.read_text()
            for node in ast.parse(text).body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == obj.__name__:
                    return ast.get_source_segment(text, node)
        return ''


def describe(name):
    obj = api_object(name)
    try:
        params = []
        for p in inspect.signature(obj).parameters.values():
            default = p.default
            if default is inspect.Parameter.empty:
                default = '<required>'
            elif callable(default):
                default = default.__module__ + '.' + default.__qualname__
            else:
                default = repr(default)
            params.append([p.name, p.kind.name, default])
    except (ValueError, TypeError):
        params = None  # C builtinの未提供signatureはdoc/C source監査で明示する。
    source = api_source(obj)
    return {'available': obj is not None, 'parameters': params,
            'source_sha256': hashlib.sha256(source.encode()).hexdigest() if source else None,
            'doc_sha256': hashlib.sha256((getattr(obj, '__doc__', None) or '').encode()).hexdigest()}


def verify_inventory(runner, root):
    inventory = json.loads((HERE / 'callback-api-inventory.json').read_text())
    assert list(sys.version_info[:3]) == inventory['runtime']
    tables = classifier_tables()
    assert api_names(tables) == set(inventory['apis']), '許可APIの追加/削除にはcallback再監査が必要'
    probes = 0
    for name, record in inventory['apis'].items():
        actual = describe(name)
        assert actual == record['runtime_binding'], (name, '署名/doc/実装変更: 再監査が必要')
        callbacks = record['callbacks']
        canonical = name.removeprefix('builtins.')
        expected_slots = tuple(c['position'] for c in callbacks if c['position'] is not None)
        assert tables['callback_slots'].get(canonical, ()) == expected_slots, name
        params = actual['parameters']
        # callable default、source内の引数直接call、callback語彙の署名引数も独立に拾う。
        detected = set()
        if params:
            obj = api_object(name)
            for p in inspect.signature(obj).parameters.values():
                if (p.default is not inspect.Parameter.empty and callable(p.default)) or p.name in tables['callback_keywords']:
                    detected.add(p.name)
            source = api_source(obj)
            if source:
                detected |= {n.func.id for n in ast.walk(ast.parse(source))
                             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id in {p[0] for p in params}}
        assert detected <= {c['name'] for c in callbacks}, (name, detected)
        for c in callbacks:
            assert canonical in tables['callback_slots'], name  # keyword検査のgate漏れも防ぐ。
            assert c['name'] in tables['callback_keywords'] or (name.startswith('json.') and c['name'] == 'default')
            if params:
                parameter = next(p for p in params if p[0] == c['name'])
                positional = [p[0] for p in params if p[1] in ('POSITIONAL_ONLY', 'POSITIONAL_OR_KEYWORD')]
                actual_position = positional.index(c['name']) if c['name'] in positional else None
                assert actual_position == c['position'], (name, c)
            prefix = '' if '.' not in name else 'import ' + name.split('.')[0] + '; '
            for callback in ('print', 'open'):
                expressions = [record['args'] + [f"{c['name']}={callback}"]]
                if c['position'] is not None:
                    expressions.append(c['before'] + [callback])
                for args in expressions:
                    code = prefix + name + '(' + ','.join(args) + ')'
                    findings = runner._fixed_python_code_attempts(code, root)
                    assert any(f['reason'] == 'python_callback_effects_unclassified' for f in findings), code
                    probes += 1
    print(f"v15 API inventory: {len(inventory['apis'])} APIs / {probes} callback probes PASS", flush=True)
