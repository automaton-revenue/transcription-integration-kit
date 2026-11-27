# Transcription API specification

The live endpoint and documentation were checked during this task. The unpaid request below returned HTTP 402 with a valid x402 v2 payment challenge.

## Endpoint

- **Method/path:** `GET /transcribe`
- **Base URL:** `https://agent-tools-x402.automaton-agent.workers.dev`
- **Query:** required `url` — public `http(s)` URL of the audio or video file. URL-encode it when constructing the request. No other query parameters are documented.
- **Authentication/payment:** no API key or account. The first unpaid request needs no special request header and returns `402 Payment Required`. The challenge is present as a JSON response body and as base64 JSON in the `PAYMENT-REQUIRED` response header. After payment, retry the same request with x402 v2 `PAYMENT-SIGNATURE` header supplied by an x402-capable client. `PAYMENT-REQUIRED` is server-to-client; it is not itself proof/payment.
- **Price:** `$0.03` USDC per completed transcription, on Base (`eip155:8453`). Challenge amount is `30000` atomic units (USDC has 6 decimals); USDC asset `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`; recipient `0x528eB355837529314A28ab87a3A479Ad857e8698`; scheme `exact`; max timeout 120 seconds. No charge for invalid input (400) or unreachable upstream (502), per service docs.
- **Model:** `@cf/openai/whisper-large-v3-turbo`.

## Response format

A successful response is JSON. Example shown in the live 402 challenge's Bazaar metadata:

```json
{
  "url": "https://example.com/podcast.mp3",
  "text": "Welcome to the show. Today we talk about agents.",
  "language": "en",
  "durationSeconds": 4.2,
  "words": 9,
  "segments": [
    {"start": 0, "end": 4.2, "text": "Welcome to the show. Today we talk about agents."}
  ],
  "vtt": "WEBVTT\n\n00:00.000 --> 00:04.200\nWelcome to the show. Today we talk about agents.",
  "model": "@cf/openai/whisper-large-v3-turbo"
}
```

Fields include source URL, transcription text, language, duration in seconds, word count, timestamped segments, WebVTT subtitles, and model identifier. The JSON example is from endpoint challenge metadata; the unpaid request did not invoke transcription.

## Errors and x402 challenge

| HTTP | Meaning / action |
|---|---|
| `400` | Invalid input; not charged. The published specification does not enumerate specific error-body properties. |
| `402` | Payment Required (x402 v2). JSON body includes `x402Version: 2`, error, resource, and `accepts` requirements. Header `PAYMENT-REQUIRED` contains base64-encoded JSON challenge. Pay via an x402 client and retry with `PAYMENT-SIGNATURE`. |
| `502` | Upstream unreachable; not charged. |

Observed challenge details: `scheme: exact`, `network: eip155:8453`, `amount: 30000`, `asset: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, `payTo: 0x528eB355837529314A28ab87a3A479Ad857e8698`, `maxTimeoutSeconds: 120`, `extra: {"name":"USD Coin","version":"2"}`. Challenge extensions include Bazaar input/output metadata.

## Working unpaid curl request (returns 402)

This makes no payment and was verified to return HTTP 402 and a valid challenge. The sample URL is illustrative; the API issues the payment challenge before an unpaid operation is completed.

```sh
curl -i --get 'https://agent-tools-x402.automaton-agent.workers.dev/transcribe' \
  --data-urlencode 'url=https://example.com/sample.mp3'
```

The live request returned `HTTP 402 Payment Required`; its decoded challenge specified the values above and `$0.03` in the description. To inspect the challenge header locally, save response headers and base64-decode `PAYMENT-REQUIRED` (header name is case-insensitive). Do not send a made-up signature: a valid x402 client must create and submit `PAYMENT-SIGNATURE`.

## Python example

Basic unpaid probe, challenge display, and shape for a payment-enabled retry (the latter requires a legitimate signature from an x402 client):

```python
import base64
import json
import requests

endpoint = "https://agent-tools-x402.automaton-agent.workers.dev/transcribe"
params = {"url": "https://example.com/sample.mp3"}
r = requests.get(endpoint, params=params, timeout=30)
print(r.status_code)  # 402 on first unpaid request
print(r.json())       # challenge body

encoded = r.headers.get("PAYMENT-REQUIRED")
if encoded:
    # Header value is base64 JSON; padding may be omitted by some implementations.
    encoded += "=" * (-len(encoded) % 4)
    print(json.loads(base64.b64decode(encoded)))

# After using an x402-capable client to pay/sign the challenge, retry:
# signed_headers = {"PAYMENT-SIGNATURE": payment_signature_from_x402_client}
# result = requests.get(endpoint, params=params, headers=signed_headers, timeout=120)
# result.raise_for_status()
# print(result.json()["text"])
```

## Node.js example

Built-in `fetch` can inspect the unpaid challenge. Use an x402-compatible payment client/wallet for the signed retry; the signature is deliberately not fabricated here.

```js
const endpoint = new URL("https://agent-tools-x402.automaton-agent.workers.dev/transcribe");
endpoint.searchParams.set("url", "https://example.com/sample.mp3");

const response = await fetch(endpoint);
console.log(response.status); // 402 on first unpaid request
const challenge = await response.json();
console.log(challenge);

const encoded = response.headers.get("payment-required");
if (encoded) {
  const decoded = JSON.parse(Buffer.from(encoded, "base64").toString("utf8"));
  console.log(decoded);
}

// After a legitimate x402 client creates the required payment signature:
// const paid = await fetch(endpoint, {
//   headers: { "PAYMENT-SIGNATURE": signatureFromX402Client }
// });
// if (!paid.ok) throw new Error(`HTTP ${paid.status}: ${await paid.text()}`);
// const result = await paid.json();
// console.log(result.text, result.vtt);
```

## Sources

- OpenAPI document: https://agent-tools-x402.automaton-agent.workers.dev/openapi.json
- Service/LLM index: https://agent-tools-x402.automaton-agent.workers.dev/llms.txt
- Live unpaid 402 challenge verified with GET `https://agent-tools-x402.automaton-agent.workers.dev/transcribe?url=https%3A%2F%2Fexample.com%2Fsample.mp3`
