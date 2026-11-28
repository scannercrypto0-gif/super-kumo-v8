"""Read warehouse through the existing Core/Factory HistoricalLibrary interface.

Historical Scanner #253 requires separate native original admission; this
adapter does not issue #245/#253 custody/query receipts. It exposes real native
HistoricalBars for research consumers sharing HistoricalLibrary.
"""
import dataclasses
from hashlib import sha256

from .storage import canonical, need


def register_window(warehouse, library, *, dataset_id, interval, start_ms, end_ms, cutoff_ms):
    from research_wp_r0.historical_library import (
        HistoricalBar, BarQuality, SourceType, DataAvailabilityKind, validate_bars,
    )
    read = warehouse.query(interval, start_ms, end_ms, cutoff_ms=cutoff_ms,
                           max_bars=4096, include_registry=True)
    projected = read['bars']
    bars = [HistoricalBar(
        symbol='BTCUSDT', interval=interval, bar_open=row['open_ms'],
        bar_close=row['close_exclusive_ms'] - 1,
        **dict(zip(('open', 'high', 'low', 'close', 'volume'),
                   (float(row[k]) for k in ('o', 'h', 'l', 'c', 'v')))),
        quality=BarQuality.FINAL, source=SourceType.ARCHIVE,
        source_label='BINANCE_VISION_RETROSPECTIVE_NON_PIT',
        observation_cutoff_ms=row['available_at_ms'], ingest_time_ms=None,
        availability_kind=DataAvailabilityKind.RETROSPECTIVE,
    ) for row in projected]
    validated, manifest = validate_bars(bars, 'BTCUSDT', interval)
    manifest = dataclasses.replace(manifest, dataset_id=dataset_id,
                                   source_hash=sha256(canonical(dict(
                                       bars=projected,
                                       registry_sha256=read['registry']['snapshot_sha256'],
                                       event_watermark=read['registry']['event_watermark']))).hexdigest())
    return library.register(dataset_id, validated, manifest)


def inspect_consumer_boundary():
    return dict(historical_library='NATIVE_RESEARCH_READ_AVAILABLE',
                core_245_253_original_custody='SEPARATE_NATIVE_ADMISSION_REQUIRED',
                scanner_e_historical='WAIT_NATIVE_CORE_RECEIPTS',
                factory='HISTORICAL_LIBRARY_RESEARCH_ONLY',
                scientific_pit_oos='NOT_ATTESTED', trading_authority='NONE')
