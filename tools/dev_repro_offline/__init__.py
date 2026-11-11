"""
AQL-CLAUDE-DEV-ENV-REPRO-001 — tools/dev_repro_offline
Issue: #212  Branch: feat/aql-dev-repro-offline-212

OFFLINE, READ-ONLY developer environment reproducibility toolkit.

PURPOSE
-------
- Deterministic environment fingerprinting
- SHA-pinned test manifest cataloguing
- Non-mutating preflight checks
- Allowlist-gated subprocess test runner
- Immutable evidence bundles with tamper detection
- Honest W1 result classification (separate ≠ integrated)
- Cross-platform portability wrappers
- Offline failure triage rules
- Adversarial / reliability tests
- One-command operator workflow

SEPARATION GUARANTEE
--------------------
This package NEVER imports from:
  src/aql/**
  research_wp_r0/**
  src/aql/observation/**
  src/aql/collector/**
  src/aql/delivery/**
  src/aql/journal/**
  src/aql/recovery/**
  src/aql/storage/**
  src/aql/archive/**

It NEVER:
  - Checks out, rebases, merges, or cherry-picks any branch or PR
  - Writes GitHub objects
  - Downloads real market data
  - Runs commands that mutate repo fixtures
  - Claims combined W1 integration is verified
  - Merges, deploys, or activates live trading
"""

# Explicit non-import declarations
_PROTECTED_PREFIXES = (
    "src.aql",
    "research_wp_r0",
)

__version__ = "0.1.0"
__issue__ = "#212"
