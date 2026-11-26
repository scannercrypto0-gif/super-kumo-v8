"""ATLAS Quant Lab — Offline Scanner Engine V1.

AQL-CLAUDE-SCANNER-ENGINE-001
Task: Build a complete, independent offline Scanner subsystem.
Namespace: tools/scanner_engine_offline/**
Stage: P0 (RETROSPECTIVE_NON_PIT synthetic development data)

This package is an ISOLATED research tool.  It does NOT:
 - modify src/aql/** or research_wp_r0/**
 - connect to Binance or any live network endpoint
 - create Signal Events, execute trades, or produce production outputs
 - share state with the running pipeline

All outputs are deterministic and content-addressed (SHA-256 canonical JSON).
"""

__version__ = "0.1.0-draft"
__task__ = "AQL-CLAUDE-SCANNER-ENGINE-001"
