"""Reproducible static source inventory, never proof of dynamic-call completeness.

Every tracked non-test Python file in the pinned tree is parsed. All function,
class, import and call locations are retained; receiver dispatch remains unresolved.
No source execution, network access, strategy selection or evidence promotion.
"""
import argparse
import ast
import hashlib
import json
import subprocess


def inventory(ref):
    commit = subprocess.check_output(['git', 'rev-parse', ref+'^{commit}'], text=True).strip()
    tree = subprocess.check_output(['git', 'rev-parse', commit+'^{tree}'], text=True).strip()
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit], text=True).splitlines()
    files = []
    excluded = []
    for path in paths:
        if not path.endswith('.py'):
            continue
        if (path.split('/')[-1].startswith('test_') or '/tests/' in '/'+path
                or path.startswith('integration_tests/') or path.endswith('/conftest.py')):
            excluded.append(path)
            continue
        raw = subprocess.check_output(['git', 'show', commit+':'+path])
        root = ast.parse(raw, filename=path)
        imports, calls, definitions, dynamic = [], [], [], []
        class Walk(ast.NodeVisitor):
            def __init__(self): self.scope = []
            def visit_ClassDef(self, node):
                definitions.append(dict(line=node.lineno, name='.'.join(self.scope+[node.name]), kind='class'))
                self.scope.append(node.name); self.generic_visit(node); self.scope.pop()
            def visit_FunctionDef(self, node):
                definitions.append(dict(line=node.lineno, name='.'.join(self.scope+[node.name]), kind='function'))
                self.scope.append(node.name); self.generic_visit(node); self.scope.pop()
            visit_AsyncFunctionDef = visit_FunctionDef
            def visit_Import(self, node):
                imports.extend(dict(line=node.lineno, module=a.name, alias=a.asname) for a in node.names)
            def visit_ImportFrom(self, node):
                imports.extend(dict(line=node.lineno, module='.'*node.level+(node.module or ''), name=a.name, alias=a.asname) for a in node.names)
            def visit_Call(self, node):
                name=ast.unparse(node.func)
                item=dict(line=node.lineno, caller='.'.join(self.scope) or '<module>', target=name)
                calls.append(item)
                if name in {'getattr','setattr','eval','exec','__import__'} or 'importlib' in name:
                    dynamic.append(item)
                self.generic_visit(node)
        Walk().visit(root)
        files.append(dict(path=path, sha256=hashlib.sha256(raw).hexdigest(),
                          imports=imports, definitions=definitions, calls=calls, dynamic_sites=dynamic))
    return dict(schema='factory-static-call-inventory-1', commit=commit, tree=tree,
                scope='ALL_TRACKED_NONTEST_PYTHON_AT_PINNED_TREE',
                dynamic_completeness=False,
                limits=['Attribute receiver types and external callers not proven by AST',
                        'Manual call-chain dispositions are a separate reviewed document',
                        'No proof of runtime execution or empirical acceptance'],
                files=files, excluded_test_paths=excluded)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--ref', required=True)
    parser.add_argument('--output', required=True); args=parser.parse_args()
    report=inventory(args.ref)
    with open(args.output, 'x', encoding='utf-8', newline='\n') as out:
        json.dump(report, out, sort_keys=True, separators=(',',':'), allow_nan=False)
        out.write('\n')
    print(json.dumps(dict(commit=report['commit'], files=len(report['files']),
                         calls=sum(len(f['calls']) for f in report['files']),
                         dynamic_sites=sum(len(f['dynamic_sites']) for f in report['files']))))
