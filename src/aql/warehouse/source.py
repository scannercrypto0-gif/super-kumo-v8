"""Bounded Binance Vision HTTPS metadata and resumable source acquisition.

No exchange REST/WS calls. A caller must supply scoped permission references.
Checksums establish integrity against the fetched publisher object, not a
third-party attestation or historical point-in-time availability.
"""
from datetime import date, datetime, timezone
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from xml.etree import ElementTree as ET
import os

from .storage import need, seal

HOST = 'https://data.binance.vision/'
LIST_HOST = 'https://s3-ap-northeast-1.amazonaws.com/data.binance.vision'
KEY = re.compile(r'data/spot/(monthly|daily)/klines/BTCUSDT/1m/(BTCUSDT-1m-(\d{4}-\d{2}(?:-\d{2})?)\.zip)')
MAX_ZIP = 64 * 1024 * 1024
MAX_XML = 4 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('SOURCE_REDIRECT_DENIED')


class VisionHTTP:
    def __init__(self, *, authority, opener=None):
        need(type(authority) is dict and all(type(authority.get(k)) is str
             and authority[k].strip() for k in ('bulk_download_ref', 'source_rights_ref',
                                               'network_permission_ref')), 'SOURCE_AUTHORIZATION_REQUIRED')
        self.authority = dict(authority)
        self.opener = opener or build_opener(NoRedirect()).open
        self.last = 0.0

    def open(self, url, headers=None):
        need(url.startswith(HOST + 'data/spot/') or url.startswith(LIST_HOST + '?'),
             'SOURCE_HOST_DENIED')
        delay = max(0, 0.25 - (time.monotonic() - self.last))
        if delay:
            time.sleep(delay)
        self.last = time.monotonic()
        return self.opener(Request(url, headers=headers or {}), timeout=30)

    def small(self, url, maximum):
        with self.open(url) as response:
            need(response.status == 200, 'SOURCE_HTTP_STATUS')
            raw = response.read(maximum + 1)
        need(len(raw) <= maximum, 'SOURCE_RESPONSE_BOUND')
        return raw

    def discover(self, *, now_ms):
        """List all monthly and daily keys, keeping snapshot completeness explicit."""
        out = []
        for cadence in ('monthly', 'daily'):
            prefix = f'data/spot/{cadence}/klines/BTCUSDT/1m/'
            token = None
            seen = set()
            for _ in range(100):
                args = {'list-type': '2', 'prefix': prefix, 'max-keys': '1000'}
                if token:
                    args['continuation-token'] = token
                raw = self.small(LIST_HOST + '?' + urlencode(args), MAX_XML)
                need(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw, 'LIST_XML_UNSAFE')
                root = ET.fromstring(raw)
                def txt(node, key):
                    found = node.find('{*}' + key)
                    return None if found is None else found.text
                for item in root.findall('{*}Contents'):
                    key = txt(item, 'Key')
                    if not key or not KEY.fullmatch(key):
                        continue
                    start, end = archive_window(key)
                    if end <= now_ms:
                        size = int(txt(item, 'Size'))
                        need(0 < size <= MAX_ZIP, 'SOURCE_ZIP_BOUND')
                        out.append(dict(key=key, size=size, start_ms=start, end_ms=end,
                                        last_modified=txt(item, 'LastModified')))
                if txt(root, 'IsTruncated') == 'false':
                    break
                token = txt(root, 'NextContinuationToken')
                need(token and token not in seen, 'LIST_PAGINATION_INVALID')
                seen.add(token)
            else:
                raise ValueError('LIST_PAGE_BOUND')
        need(out and len({r['key'] for r in out}) == len(out), 'LIST_EMPTY_OR_DUPLICATE')
        return sorted(out, key=lambda r: (r['start_ms'], r['key']))

    def acquire(self, warehouse, key, *, expected_size=None):
        need(KEY.fullmatch(key) is not None, 'ARCHIVE_KEY_INVALID')
        name = KEY.fullmatch(key).group(2)
        checksum = self.small(HOST + key + '.CHECKSUM', 512)
        matched = re.fullmatch(rb'([a-fA-F0-9]{64})[ \t]+\*?' + re.escape(name.encode()) + rb'\s*', checksum)
        need(matched is not None, 'PUBLISHER_CHECKSUM_SCHEMA')
        pin = matched.group(1).decode().lower()
        final = warehouse.path(f'raw/{pin}.zip')
        if final.exists():
            need(seal(final.read_bytes()) == pin, 'RETAINED_RAW_CORRUPT')
        else:
            part = warehouse.path(f'raw/{pin}.part')
            offset = part.stat().st_size if part.exists() else 0
            need(offset <= MAX_ZIP, 'PART_BOUND')
            headers = {'Range': f'bytes={offset}-'} if offset else {}
            try:
                response = self.open(HOST + key, headers)
            except HTTPError as exc:
                if exc.code == 416 and offset and seal(part.read_bytes()) == pin:
                    response = None
                else:
                    raise
            if response is not None:
                with response:
                    if response.status == 206:
                        m = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                        need(m is not None and int(m[1]) == offset
                             and int(m[2]) == int(m[3]) - 1, 'RANGE_IDENTITY_INVALID')
                        total = int(m[3])
                    else:
                        need(response.status == 200, 'SOURCE_HTTP_STATUS')
                        # Servers ignoring Range safely restart this private scratch.
                        offset = 0
                        total = int(response.headers.get('Content-Length', '0'))
                    need(0 < total <= MAX_ZIP and (expected_size is None or total == expected_size),
                         'SOURCE_LENGTH_INVALID')
                    warehouse.budget(total - offset)
                    with part.open('ab' if offset else 'wb') as stream:
                        remaining = total - offset
                        while remaining:
                            block = response.read(min(1024 * 1024, remaining))
                            need(block, 'DOWNLOAD_INTERRUPTED')
                            warehouse.budget(len(block))
                            stream.write(block)
                            stream.flush()
                            os.fsync(stream.fileno())
                            remaining -= len(block)
                        need(not response.read(1), 'SOURCE_LENGTH_OVERFLOW')
            if seal(part.read_bytes()) != pin:
                destination = warehouse.path(f'quarantine/{pin}-{seal(part.read_bytes())}.zip')
                need(not destination.exists(), 'QUARANTINE_ALREADY_PRESENT')
                os.replace(part, destination)
                raise ValueError('PUBLISHER_CHECKSUM_MISMATCH')
            os.replace(part, final)
        warehouse.write_once(f'raw/{seal(checksum)}.CHECKSUM', checksum)
        return final, checksum


def archive_window(key):
    m = KEY.fullmatch(key)
    need(m is not None, 'ARCHIVE_KEY_INVALID')
    token = m.group(3)
    need((m.group(1) == 'daily') == (len(token) == 10), 'ARCHIVE_CADENCE_INVALID')
    start = date.fromisoformat(token if len(token) == 10 else token + '-01')
    if len(token) == 10:
        from datetime import timedelta
        end = start + timedelta(days=1)
    else:
        end = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    epoch = lambda x: int(datetime(x.year, x.month, x.day, tzinfo=timezone.utc).timestamp() * 1000)
    return epoch(start), epoch(end)
