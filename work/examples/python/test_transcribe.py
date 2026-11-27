"""Unit tests for the x402 transcription client; no network or wallet required."""

import unittest
from unittest.mock import patch

import httpx

import transcribe


class TranscribeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.url = "https://example.com/sample.mp3"
        self.transport = httpx.MockTransport(self.handler)
        self.client = httpx.Client(transport=self.transport)

    def tearDown(self) -> None:
        self.client.close()

    def handler(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": self.url, "text": "hello", "language": "en"})

    def test_success_without_payment(self) -> None:
        result = transcribe.transcribe(self.url, client=self.client)
        self.assertEqual(result["text"], "hello")

    def test_payment_required_without_key_reports_error(self) -> None:
        self.client.close()
        self.client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(402, json={"x402Version": 2, "accepts": [{"scheme": "exact"}]})
            )
        )
        with self.assertRaisesRegex(transcribe.TranscriptionError, "set X402_PRIVATE_KEY"):
            transcribe.transcribe(self.url, client=self.client)

    def test_payment_challenge_signs_and_retries(self) -> None:
        calls: list[httpx.Request] = []
        challenge = {
            "x402Version": 2,
            "accepts": [{
                "scheme": "exact",
                "network": "eip155:8453",
                "amount": "30000",
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "payTo": "0x528eB355837529314A28ab87a3A479Ad857e8698",
                "maxTimeoutSeconds": 120,
                "extra": {"name": "USD Coin", "version": "2"},
            }],
        }

        def paid_handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(402, json=challenge)
            return httpx.Response(200, json={"url": self.url, "text": "paid transcript"})

        self.client.close()
        self.client = httpx.Client(transport=httpx.MockTransport(paid_handler))
        with patch.object(transcribe, "_payment_signature", return_value="mock-signature") as signer:
            result = transcribe.transcribe(self.url, "0x" + "11" * 32, client=self.client)
        self.assertEqual(result["text"], "paid transcript")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].headers["PAYMENT-SIGNATURE"], "mock-signature")
        signer.assert_called_once_with(challenge["accepts"][0], "0x" + "11" * 32)

    def test_invalid_url_is_rejected_before_request(self) -> None:
        with self.assertRaisesRegex(ValueError, r"absolute http\(s\) URL"):
            transcribe.transcribe("file:///tmp/audio.mp3", client=self.client)


if __name__ == "__main__":
    unittest.main()
