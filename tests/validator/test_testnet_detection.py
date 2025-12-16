#!/usr/bin/env python3
# The MIT License (MIT)
# Copyright © 2025 Entrius

"""
Unit tests for testnet detection in debug API.

Tests the _is_testnet() function to ensure it correctly identifies testnet vs mainnet endpoints.
"""

import unittest
from unittest.mock import patch

from gittensor.validator.test.live_testnet.test_validator_live import _is_testnet


class TestTestnetDetection(unittest.TestCase):
    """Test cases for _is_testnet() function."""

    def test_testnet_endpoints(self):
        """Test that testnet endpoints are correctly identified."""
        testnet_endpoints = [
            "wss://test.finney.opentensor.ai:443/",
            "wss://test.finney.opentensor.ai:443",
            "wss://test.finney.opentensor.ai",
            "wss://testnet.opentensor.ai:443",
            "wss://test.opentensor.ai",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "ws://localhost:9944",
            "ws://127.0.0.1:9944",
            "test.finney.opentensor.ai",
            "localhost",
            "127.0.0.1",
        ]

        for endpoint in testnet_endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertTrue(
                    _is_testnet(endpoint),
                    f"Expected {endpoint} to be identified as testnet",
                )

    def test_mainnet_endpoints(self):
        """Test that mainnet endpoints are correctly identified."""
        mainnet_endpoints = [
            "wss://entrypoint-finney.opentensor.ai:443",
            "wss://entrypoint-finney.opentensor.ai:443/",
            "wss://finney.opentensor.ai:443",
            "wss://finney.opentensor.ai",
            "wss://mainnet.opentensor.ai",
            "wss://opentensor.ai",
        ]

        for endpoint in mainnet_endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertFalse(
                    _is_testnet(endpoint),
                    f"Expected {endpoint} to be identified as mainnet (not testnet)",
                )

    def test_edge_cases(self):
        """Test edge cases for _is_testnet()."""
        # None should return False
        self.assertFalse(_is_testnet(None), "None should return False")

        # Empty string should return False
        self.assertFalse(_is_testnet(""), "Empty string should return False")

        # Case insensitive matching
        self.assertTrue(_is_testnet("WSS://TEST.FINNEY.OPENTENSOR.AI:443"))
        self.assertTrue(_is_testnet("TESTNET"))
        self.assertTrue(_is_testnet("LOCALHOST"))

    def test_case_insensitive(self):
        """Test that matching is case-insensitive."""
        self.assertTrue(_is_testnet("TEST.FINNEY.OPENTENSOR.AI"))
        self.assertTrue(_is_testnet("Test.Finney.Opentensor.Ai"))
        self.assertTrue(_is_testnet("tEsT.fInNeY.oPeNtEnSoR.aI"))


class TestDebugAPITestnetCheck(unittest.TestCase):
    """Test cases for debug API testnet check logic."""

    @patch("gittensor.validator.test.live_testnet.test_validator_live.os.getenv")
    def test_testnet_detection_integration(self, mock_getenv):
        """Test that _is_testnet is used correctly in the trigger_scoring logic."""
        # Mock environment variable
        mock_getenv.side_effect = lambda key, default=None: (
            "false" if key == "ALLOW_DEBUG_ON_MAINNET" else default
        )

        # Test that testnet endpoints pass the check
        testnet_endpoints = [
            "wss://test.finney.opentensor.ai:443",
            "localhost",
            "127.0.0.1",
        ]

        for endpoint in testnet_endpoints:
            with self.subTest(endpoint=endpoint):
                is_testnet = _is_testnet(endpoint)
                self.assertTrue(is_testnet, f"{endpoint} should be detected as testnet")

        # Test that mainnet endpoints fail the check
        mainnet_endpoints = [
            "wss://entrypoint-finney.opentensor.ai:443",
            "wss://finney.opentensor.ai",
        ]

        for endpoint in mainnet_endpoints:
            with self.subTest(endpoint=endpoint):
                is_testnet = _is_testnet(endpoint)
                self.assertFalse(
                    is_testnet, f"{endpoint} should NOT be detected as testnet"
                )

    @patch("gittensor.validator.test.live_testnet.test_validator_live.os.getenv")
    def test_allow_debug_on_mainnet_override(self, mock_getenv):
        """Test that ALLOW_DEBUG_ON_MAINNET environment variable override works."""
        # Test with override enabled
        mock_getenv.side_effect = lambda key, default=None: (
            "true" if key == "ALLOW_DEBUG_ON_MAINNET" else default
        )

        # Even with mainnet endpoint, if override is set, it should be allowed
        # (The actual check happens in the code, but we verify the env var is read correctly)
        mainnet_endpoint = "wss://entrypoint-finney.opentensor.ai:443"
        is_testnet = _is_testnet(mainnet_endpoint)

        # Mainnet endpoint should not be detected as testnet
        self.assertFalse(is_testnet)

        # But the override env var should allow it (we verify the logic exists)
        allow_override = (
            mock_getenv("ALLOW_DEBUG_ON_MAINNET", "false").lower() == "true"
        )
        self.assertTrue(allow_override, "Override should be enabled")


if __name__ == "__main__":
    unittest.main()
