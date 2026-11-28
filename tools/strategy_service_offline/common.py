from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from hashlib import sha256
from dataclasses import dataclass
from research_wp_r0.strategy_definition import canonical, digest


class BoundaryError(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise BoundaryError(reason)


def raw_sha(raw):
    return sha256(raw).hexdigest()


def decode(raw):
    require(len(raw) <= 8 * 1024 * 1024, 'INPUT_BYTE_LIMIT')
    def pairs(items):
        out = {}
        for k,v in items:
            require(k not in out, 'DUPLICATE_JSON_KEY')
            out[k] = v
        return out
    def reject(x):
        raise BoundaryError('NONFINITE_JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def confined(root, relative):
    root = Path(root).resolve()
    p = Path(relative)
    require(not p.is_absolute() and '..' not in p.parts, 'PATH_ESCAPE')
    target = root/p
    require(not any(x.is_symlink() for x in [target,*target.parents]), 'SYMLINK_PATH')
    require(target.resolve().is_relative_to(root), 'PATH_ESCAPE')
    return target


def read(path):
    p = Path(path)
    require(p.stat().st_size <= 8 * 1024 * 1024, 'INPUT_BYTE_LIMIT')
    return p.read_bytes()


@dataclass(frozen=True)
class Frozen:
    payload: bytes

    @classmethod
    def build(cls, obj):
        return cls(canonical(obj))

    @property
    def data(self):
        return decode(self.payload)

    @property
    def sha256(self):
        return raw_sha(self.payload)

    def receipt(self):
        return {'payload': self.data, 'sha256': self.sha256}

    @classmethod
    def restore(cls, obj):
        item = cls.build(obj['payload'])
        require(item.sha256 == obj['sha256'], 'FROZEN_DIGEST_DRIFT')
        return item


class Dependencies:
    def __init__(self, lock_path, expected_sha, roots):
        raw = read(Path(lock_path))
        require(raw_sha(raw) == expected_sha, 'DEPENDENCY_LOCK_SHA')
        lock = decode(raw)
        require(lock['schema'] == 'aql.work.strategy-service.dependencies.v1', 'DEPENDENCY_VERSION')
        require(set(roots) == set(lock['components']), 'MISSING_DEPENDENCY')
        self.roots = {k: str(Path(v).resolve()) for k,v in roots.items()}
        self.lock = lock
        for name,spec in lock['components'].items():
            require(re.fullmatch('[0-9a-f]{40}', spec['commit_sha']) is not None, 'COMMIT_SHA')
            for path,expected in spec['files'].items():
                require(raw_sha(read(confined(roots[name],path))) == expected,
                        'DEPENDENCY_DRIFT:'+name+':'+path)
        store_path = Path(self.roots['work'])/'tools/research_integration_harness/harness.py'
        spec = importlib.util.spec_from_file_location('_retained_work_receipt_store', store_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.store_type = module.ReceiptStore

    def call(self, name, action, body):
        raw = canonical(body)
        require(len(raw) <= 8*1024*1024, 'WORKER_INPUT_LIMIT')
        script = Path(__file__).with_name('worker.py')
        r = subprocess.run([sys.executable,'-I',str(script),name,action,self.roots[name]],
                           input=raw,capture_output=True,timeout=30)
        if r.returncode:
            lines = r.stderr.decode(errors='replace').splitlines()
            raise BoundaryError('DEPENDENCY_REFUSED:'+name+':'+(lines[-1][:200] if lines else 'ERROR'))
        return decode(r.stdout)


class RunJournal:
    """Narrow TEST_ONLY result/attempt adapter over retained Work ReceiptStore.

    Indexed hard links publish verified immutable result objects, never a global
    research/custody journal. No mutable counters or wall-clock IDs.
    """
    def __init__(self, root, deps):
        self.root = Path(root)
        self.store = deps.store_type(self.root/'objects')
        self.index = self.root/'index'
        self.index.mkdir(parents=True,exist_ok=True)
        require(not self.index.is_symlink(), 'JOURNAL_ALIAS')

    def _path(self, kind, key):
        require(kind in {'claim','result'} and re.fullmatch('[0-9a-f]{64}',key), 'JOURNAL_KEY')
        return self.index/(key+'.'+kind)

    def get(self, kind, key):
        p = self._path(kind,key)
        require(not p.is_symlink(), 'JOURNAL_ALIAS')
        if not p.exists(): return None
        value = decode(read(p))
        content = self.root/'objects'/(raw_sha(read(p))+'.json')
        require(content.is_file() and read(content)==read(p), 'JOURNAL_CONTENT_TAMPER')
        return value

    def put(self, kind, key, value):
        p = self._path(kind,key)
        prior = self.get(kind,key)
        if prior is not None:
            require(canonical(prior)==canonical(value), 'IMMUTABLE_REPLAY_CONFLICT')
            return prior
        require(sum(1 for _ in self.index.iterdir()) < 2048, 'JOURNAL_LIMIT')
        content_key = self.store.put(value)
        try:
            os.link(self.root/'objects'/(content_key+'.json'),p)
        except FileExistsError:
            require(self.get(kind,key)==value,'IMMUTABLE_REPLAY_CONFLICT')
        if hasattr(os,'O_DIRECTORY'):
            fd=os.open(self.index,os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        return self.get(kind,key)

    def record_attempt(self, event):
        key = digest({'native_attempt_event':event})
        self.put('result',key,{'schema':'aql.work.native-attempt-event.v1','event':event})
