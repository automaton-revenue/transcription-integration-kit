#!/usr/bin/env python3
"""Transcribe a public audio/video URL using the x402 paid transcription API.

Usage:
  python transcribe.py https://example.com/audio.mp3
  X402_PRIVATE_KEY=0x... python transcribe.py https://example.com/audio.mp3

The service does not use an API key. A wallet private key is required to pay
when the API responds with an x402 payment challenge. Keep it in the environment
(or another secret store), never commit it to source control.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
import time
from typing import Any
from urllib.parse import urlparse

import httpx

ENDPOINT = "https://agent-tools-x402.automaton-agent.workers.dev/transcribe"
PAYMENT_REQUIRED_HEADER = "PAYMENT-REQUIRED"
PAYMENT_SIGNATURE_HEADER = "PAYMENT-SIGNATURE"


class TranscriptionError(RuntimeError):
    """Raised when the API cannot provide a transcript."""


def validate_audio_url(audio_url: str) -> str:
    """Return a normalized public HTTP(S) URL or raise ValueError."""
    parsed = urlparse(audio_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("audio URL must be an absolute http(s) URL with a hostname")
    if parsed.username or parsed.password:
        raise ValueError("audio URL must not contain embedded credentials")
    return audio_url.strip()


def _challenge_from_response(response: httpx.Response) -> dict[str, Any]:
    """Read x402 challenge JSON from the response body or encoded header."""
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        body = None
    if isinstance(body, dict) and isinstance(body.get("accepts"), list):
        return body

    encoded = response.headers.get(PAYMENT_REQUIRED_HEADER)
    if encoded:
        try:
            encoded += "=" * (-len(encoded) % 4)
            decoded = base64.b64decode(encoded, validate=True)
            challenge = json.loads(decoded)
        except (ValueError, json.JSONDecodeError) as exc:
            raise TranscriptionError("server returned an invalid PAYMENT-REQUIRED header") from exc
        if isinstance(challenge, dict):
            return challenge
    raise TranscriptionError("HTTP 402 response did not contain a usable x402 challenge")


def _accepted_requirement(challenge: dict[str, Any]) -> dict[str, Any]:
    accepts = challenge.get("accepts")
    if not isinstance(accepts, list) or not accepts:
        raise TranscriptionError("x402 challenge contains no payment requirements")
    for requirement in accepts:
        if (
            isinstance(requirement, dict)
            and requirement.get("scheme") == "exact"
            and str(requirement.get("network", "")).lower() == "eip155:8453"
        ):
            return requirement
    raise TranscriptionError("no supported exact-payment requirement for Base was offered")


def _payment_signature(requirement: dict[str, Any], private_key: str) -> str:
    """Create an EIP-3009 authorization and x402 v2 payment payload."""
    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
        from web3 import Web3
    except ImportError as exc:
        raise TranscriptionError("payment dependencies missing; install requirements.txt") from exc

    try:
        account = Account.from_key(private_key)
        chain_id = int(str(requirement["network"]).split(":", 1)[1])
        token = Web3.to_checksum_address(requirement["asset"])
        recipient = Web3.to_checksum_address(requirement["payTo"])
        amount = int(requirement["amount"])
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise TranscriptionError("x402 challenge has invalid payment requirement fields") from exc
    if amount <= 0:
        raise TranscriptionError("x402 challenge specifies an invalid payment amount")

    now = int(time.time())
    timeout = requirement.get("maxTimeoutSeconds", 120)
    try:
        valid_before = now + max(1, int(timeout))
    except (TypeError, ValueError) as exc:
        raise TranscriptionError("x402 challenge has an invalid timeout") from exc
    authorization = {
        "from": account.address,
        "to": recipient,
        "value": str(amount),
        "validAfter": str(max(0, now - 60)),
        "validBefore": str(valid_before),
        "nonce": "0x" + secrets.token_hex(32),
    }
    extra = requirement.get("extra") or {}
    domain = {
        "name": extra.get("name", "USD Coin"),
        "version": extra.get("version", "2"),
        "chainId": chain_id,
        "verifyingContract": token,
    }
    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": domain,
        "message": authorization,
    }
    try:
        signed = Account.sign_message(encode_typed_data(full_message=typed_data), private_key=private_key)
    except (ValueError, TypeError) as exc:
        raise TranscriptionError("could not sign the x402 payment authorization") from exc

    payment = {
        "x402Version": challenge_version(requirement),
        "accepted": requirement,
        "payload": {
            "authorization": authorization,
            "signature": signed.signature.hex(),
        },
    }
    return base64.b64encode(json.dumps(payment, separators=(",", ":")).encode()).decode()


def challenge_version(requirement: dict[str, Any]) -> int:
    """x402 v2 challenges use a v2 signature envelope."""
    # The requirement object itself does not carry x402Version. The API spec
    # documents this endpoint as x402 v2, so use the protocol's v2 envelope.
    del requirement
    return 2


def transcribe(
    audio_url: str,
    private_key: str | None = None,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Call the endpoint, paying a valid 402 challenge once when configured."""
    valid_url = validate_audio_url(audio_url)
    owns_client = client is None
    http = client or httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0))
    try:
        response = http.get(ENDPOINT, params={"url": valid_url})
        if response.status_code == 402:
            challenge = _challenge_from_response(response)
            if not private_key:
                raise TranscriptionError(
                    "payment required; set X402_PRIVATE_KEY to a funded Base wallet private key"
                )
            requirement = _accepted_requirement(challenge)
            # The version is fixed to v2 by the documented service contract.
            signature = _payment_signature(requirement, private_key)
            response = http.get(
                ENDPOINT,
                params={"url": valid_url},
                headers={PAYMENT_SIGNATURE_HEADER: signature},
            )
        if response.status_code >= 400:
            detail = response.text.strip()
            raise TranscriptionError(f"transcription API returned HTTP {response.status_code}: {detail}")
        try:
            result = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise TranscriptionError("transcription API returned invalid JSON") from exc
        if not isinstance(result, dict) or not isinstance(result.get("text"), str):
            raise TranscriptionError("transcription API response did not include transcript text")
        return result
    except httpx.HTTPError as exc:
        raise TranscriptionError(f"request to transcription API failed: {exc}") from exc
    finally:
        if owns_client:
            http.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transcribe a public audio/video URL via x402.")
    parser.add_argument("audio_url", help="public http(s) URL of the audio or video")
    parser.add_argument(
        "--private-key",
        default=os.environ.get("X402_PRIVATE_KEY"),
        help="Base wallet private key (prefer X402_PRIVATE_KEY environment variable)",
    )
    args = parser.parse_args(argv)
    try:
        result = transcribe(args.audio_url, args.private_key)
    except (ValueError, TranscriptionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(result["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
