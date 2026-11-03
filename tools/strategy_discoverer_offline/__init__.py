"""
ATLAS Quant Lab — Strategy Discoverer V1
Namespace: tools/strategy_discoverer_offline

Isolated offline research module.  Generates, deduplicates and packages
hypothesis candidates using only merged, stable contracts from main:

    research_wp_r0.strategy_definition   (PR #69, MERGED)
    research_wp_r0.indicator_library_v2  (PR #68, MERGED)

No connections to Factory, Scanner, Work, Core, or live data.
All outputs carry evaluation_status=NOT_EVALUATED, publishable=False,
delivery_authorized=False, factory_routing=NOT_CONNECTED.

Schema version: aql.discoverer.v1
"""

__version__ = "1.0.0-dev"
SCHEMA_VERSION = "aql.discoverer.v1"
