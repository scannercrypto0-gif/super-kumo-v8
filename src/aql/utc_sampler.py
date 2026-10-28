"""Separate collector reusing canonical SNTP diagnostics, retaining W32Time."""
from dataclasses import asdict, replace
import re
import subprocess
import sys
from aql.utc_evidence import measure_sntp


def collect(session, *, host='time.cloudflare.com', ttl_ms=60000):
    sample = measure_sntp(host, ttl_ms=ttl_ms)
    dispersion = sample.root_dispersion_ms
    raw_status = None
    synchronized = False
    # Local W32Time dispersion is required on Windows. Unsupported/localized
    # output fails UNKNOWN and is retained for operator review, never guessed.
    if sys.platform == 'win32':
        result = subprocess.run(['w32tm', '/query', '/status', '/verbose'],
                                capture_output=True, text=True, timeout=5)
        raw_status = result.stdout
        match = re.search(r'Root Dispersion:\s*([0-9]+(?:[.,][0-9]+)?)s', raw_status)
        sync = re.search(r'Leap Indicator:\s*0\b', raw_status)
        if result.returncode == 0 and match and sync:
            dispersion = max(dispersion, float(match[1].replace(',', '.'))*1000)
            synchronized = True
    sample = replace(sample, root_dispersion_ms=dispersion, synchronized=synchronized)
    return dict(observer_session=session, sample=asdict(sample),
                w32time_raw=raw_status, authentication='UNAUTHENTICATED_DIAGNOSTIC_ONLY')
