"""
tools/raw_vault_offline — offline, fixture-driven, non-production RAW market-data vault toolkit.

Issue: AQL-CLAUDE-RAW-MARKET-DATA-VAULT-001 (#207)
Branch: feat/aql-raw-vault-offline-207
Namespace: tools/raw_vault_offline/

SEPARATION GUARANTEE
--------------------
This package is wholly independent. It does NOT import from:
  - src/aql/observation/**
  - src/aql/collector/**
  - src/aql/delivery/**
  - src/aql/journal/**
  - src/aql/recovery/**
  - src/aql/storage/**
  - src/aql/archive/**   (existing production archive)
  - research_wp_r0/**

No live API, network, or exchange access. Synthetic fixture bytes only.
No production datastore. No migration. No merge authorised.
"""
__version__ = "0.1.0-dev"
NAMESPACE = "tools.raw_vault_offline"
