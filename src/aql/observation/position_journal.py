"""Offline durable event journal; no trading, price retrieval or cloud dependencies."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
from .positions import PositionContractError, PositionEvent, PositionLedger

class JournalIntegrityError(PositionContractError): pass

class DurablePositionJournal:
    """Single-writer append-only JSONL with fsync; torn trailing records fail closed.

    Caller must serialize writers externally; no cross-process locking is claimed.
    """
    def __init__(self, path):
        self.path=Path(path)
        self.ledger=PositionLedger()
        self._tail='0'*64
        self._replay()
        self._expected_size=self.path.stat().st_size if self.path.exists() else 0
    def _replay(self):
        if not self.path.exists(): return
        with self.path.open('rb') as f:
            for number,raw in enumerate(f,1):
                if not raw.endswith(b'\n'): raise JournalIntegrityError(f'torn record at line {number}')
                try:
                    row=json.loads(raw)
                    if set(row)!= {'previous','event','digest'} or row['previous']!=self._tail:
                        raise JournalIntegrityError(f'chain mismatch at line {number}')
                    material=json.dumps({'previous':row['previous'],'event':row['event']},sort_keys=True,separators=(',',':')).encode()
                    if hashlib.sha256(material).hexdigest()!=row['digest']:
                        raise JournalIntegrityError(f'checksum mismatch at line {number}')
                    e=PositionEvent(**row['event'])
                    if self.ledger.append(e)!='inserted': raise JournalIntegrityError(f'duplicate record at line {number}')
                    self._tail=row['digest']
                except (ValueError,TypeError,KeyError,UnicodeError,PositionContractError) as exc:
                    raise JournalIntegrityError(f'invalid journal line {number}') from exc
    def append(self,event):
        # Refuse stale instances and out-of-band changes before every write.
        # This detects sequential conflicts but is NOT a cross-process lock.
        current_size=self.path.stat().st_size if self.path.exists() else 0
        if current_size != self._expected_size:
            raise JournalIntegrityError('journal changed outside this writer; reopen and replay')
        # Same-size edits are also unsafe; verify the complete chain against disk.
        probe=object.__new__(DurablePositionJournal)
        probe.path=self.path
        probe.ledger=PositionLedger()
        probe._tail='0'*64
        probe._replay()
        if probe._tail != self._tail:
            raise JournalIntegrityError('journal contents changed outside this writer')
        if not isinstance(event,PositionEvent): raise PositionContractError('invalid event')
        # Validate against a disposable replay before touching durable bytes.
        candidate=PositionLedger()
        for prior in self.ledger.events.values(): candidate.append(prior)
        result=candidate.append(event)
        if result=='duplicate': return 'duplicate'
        row={'previous':self._tail,'event':asdict(event)}
        material=json.dumps(row,sort_keys=True,separators=(',',':')).encode()
        row['digest']=hashlib.sha256(material).hexdigest()
        encoded=(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open('ab') as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        self.ledger=candidate
        self._tail=row['digest']
        self._expected_size+=len(encoded)
        return 'inserted'
