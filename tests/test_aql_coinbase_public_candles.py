"""Offline source identity and finality checks for the Coinbase adapter."""
import unittest

from research_wp_r0.aql_coinbase_public_candles import (
    CoinbaseSourceError, normalize_response, parse_final_candle,
)


class CoinbaseCandleTests(unittest.TestCase):
    def setUp(self):
        self.row = [1800000000, "100", "110", "102", "108", "15"]
        self.now = (1800000000 + 900) * 1000

    def test_completed_source_is_not_binance_execution_price(self):
        candle = parse_final_candle(self.row, product_id="BTC-USD", received_at_ms=self.now)
        self.assertEqual(candle.source, "coinbase_exchange_public_rest")
        self.assertEqual(candle.product_id, "BTC-USD")
        self.assertEqual(candle.interval, "15m")
        self.assertEqual(candle.close_time_ms, self.now - 1)
        self.assertFalse(candle.executable_on_binance)
        self.assertEqual(candle.custody, "UNVERIFIED_PUBLIC_REST")

    def test_unfinished_rejected(self):
        with self.assertRaisesRegex(CoinbaseSourceError, "UNFINISHED_CANDLE"):
            parse_final_candle(self.row, product_id="BTC-USD", received_at_ms=self.now - 1)

    def test_invalid_ohlc_rejected(self):
        with self.assertRaisesRegex(CoinbaseSourceError, "INVALID_OHLCV"):
            parse_final_candle([self.row[0], 105, 110, 102, 108, 15],
                               product_id="BTC-USD", received_at_ms=self.now)

    def test_no_binance_product_impersonation(self):
        with self.assertRaisesRegex(CoinbaseSourceError, "INVALID_COINBASE_USD_PRODUCT"):
            parse_final_candle(self.row, product_id="BTCUSDT", received_at_ms=self.now)

    def test_duplicate_or_gapped_rejected(self):
        with self.assertRaisesRegex(CoinbaseSourceError, "DUPLICATE_OR_GAPPED_SOURCE"):
            normalize_response([self.row, self.row], product_id="BTC-USD", received_at_ms=self.now)

    def test_unsorted_contiguous_accepted(self):
        next_row = [self.row[0] + 900, "101", "111", "103", "109", "16"]
        bars = normalize_response([next_row, self.row], product_id="BTC-USD",
                                  received_at_ms=self.now + 900000)
        self.assertEqual(len(bars), 2)
        self.assertLess(bars[0].open_time_ms, bars[1].open_time_ms)


if __name__ == "__main__":
    unittest.main()
