# Setup and API access

This guide calls the live transcription API at `https://agent-tools-x402.automaton-agent.workers.dev/transcribe`. Unpaid calls receive HTTP 402 with an x402 payment challenge; a compatible client can sign the requested payment and retry.

## 1. Prerequisites

- Python 3.10+ and pip (Python example).
- Node.js 18+ and npm (Node example).
- A wallet with spendable USDC on **Base mainnet** (chain ID 8453; x402 network `eip155:8453`). Price is **$0.03 USDC per completed transcription**.
- A publicly reachable HTTP(S) audio/video URL.

Use a dedicated wallet and keep its private key secret. Never commit keys or paste them into shared logs. Ensure the wallet has Base mainnet USDC before making a paid call.

## 2. Get API access (x402 payment setup)

No API key or signup is required. Make a request; the initial unpaid call returns HTTP 402 and payment requirements. An x402 v2 client reads the challenge, signs the requested payment with your wallet, and retries with `PAYMENT-SIGNATURE`. `PAYMENT-REQUIRED` is the server's challenge, not a signature; do not echo it as payment. The live challenge specifies exact payment on Base (`eip155:8453`), 30,000 atomic USDC units ($0.03; six decimals), and the Base USDC contract `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`. Let the client read and honor the live challenge (including recipient) rather than hard-coding requirements.

## 3. Python example: probe and paid request

Install the official Python x402 requests and EVM extras:

```bash
python -m venv .venv
# macOS/Linux:
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install "x402[requests,evm]"
```

Set a wallet private key in your local shell. Use a funded Base wallet. macOS/Linux:

```bash
export EVM_PRIVATE_KEY=0xYOUR_FUNDED_BASE_WALLET_PRIVATE_KEY
```

Windows PowerShell:

```powershell
$env:EVM_PRIVATE_KEY = "0xYOUR_FUNDED_BASE_WALLET_PRIVATE_KEY"
```

Save as `transcribe.py`:

```python
import os
from urllib.parse import urlencode
from eth_account import Account
from x402 import x402ClientSync
from x402.http.clients import x402_requests
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client_sync

key = os.environ["EVM_PRIVATE_KEY"]
client = x402ClientSync()
register_exact_evm_client_sync(client, EthAccountSigner(Account.from_key(key)))
session = x402_requests(client)
url = "https://example.com/sample.mp3"  # Replace with a public media URL
endpoint = "https://agent-tools-x402.automaton-agent.workers.dev/transcribe?" + urlencode({"url": url})
response = session.get(endpoint, timeout=120)  # handles 402 -> sign -> retry
response.raise_for_status()
result = response.json()
print(result["text"])
print(result["vtt"])
```

Run it with `python transcribe.py`. The signed retry can spend $0.03 USDC; use only a wallet you intend to authorize for that payment. To inspect the challenge without paying, use this copy-paste runnable probe (does not use a wallet):

```bash
curl -i --get 'https://agent-tools-x402.automaton-agent.workers.dev/transcribe' --data-urlencode 'url=https://example.com/sample.mp3'
```

An unpaid probe is expected to return `402 Payment Required`.

## 4. Node.js example: automatic x402 payment

Create a project and install the official x402 fetch/EVM packages and viem:

```bash
mkdir transcribe-x402
cd transcribe-x402
npm init -y
npm pkg set type=module
npm install @x402/fetch @x402/evm viem
```

Set your funded Base wallet private key in the local shell; do not commit it. macOS/Linux:

```bash
export EVM_PRIVATE_KEY=0xYOUR_FUNDED_BASE_WALLET_PRIVATE_KEY
```

Windows PowerShell:

```powershell
$env:EVM_PRIVATE_KEY = "0xYOUR_FUNDED_BASE_WALLET_PRIVATE_KEY"
```

Save this as `transcribe.mjs`:

```js
import { x402Client, wrapFetchWithPayment } from "@x402/fetch";
import { ExactEvmScheme } from "@x402/evm/exact/client";
import { privateKeyToAccount } from "viem/accounts";

const key = process.env.EVM_PRIVATE_KEY;
if (!key) throw new Error("Set EVM_PRIVATE_KEY in your shell first");
const client = new x402Client();
client.register("eip155:8453", new ExactEvmScheme(privateKeyToAccount(key)));
const fetchWithPayment = wrapFetchWithPayment(fetch, client);
const endpoint = new URL("https://agent-tools-x402.automaton-agent.workers.dev/transcribe");
endpoint.searchParams.set("url", "https://example.com/sample.mp3"); // Replace with public media URL
const response = await fetchWithPayment(endpoint); // handles 402 -> sign -> retry
if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
const result = await response.json();
console.log(result.text);
console.log(result.vtt);
```

Run with `node transcribe.mjs`. The call authorizes a $0.03 payment if successful. The response is JSON with transcription text, language, duration, segments, WebVTT, and model.

## 5. Troubleshooting common errors

- **402 Payment Required:** Expected from an unpaid probe. For paid calls verify the x402 v2 client/wrapper and exact EVM scheme are registered for `eip155:8453`, the wallet has USDC on Base mainnet, and the client is allowed to handle the challenge. Never pass `PAYMENT-REQUIRED` as `PAYMENT-SIGNATURE`.
- **Network or timeout:** Check internet/DNS, endpoint hostname, and allow outbound HTTPS. The media URL must be public and reachable; private, expired, or blocked links can fail. Retry transient failures cautiously and inspect status before retrying paid calls.
- **Wallet/key error:** Ensure `EVM_PRIVATE_KEY` is set and is a valid key for the intended wallet; confirm funds are on Base mainnet, not Ethereum mainnet or a testnet. Keep keys private.
- **400:** Check that `url` is a valid public HTTP(S) media URL. Invalid input is not charged per the API specification.
- **502:** Upstream transcription may be unavailable; try again later. The API specification says upstream-unreachable errors are not charged.
- **Unexpected JSON/error:** Print the HTTP status and response text before assuming it is a successful transcription result.

## 6. Live API documentation

- [Live OpenAPI docs](https://agent-tools-x402.automaton-agent.workers.dev/openapi.json)
- [Service index / LLM docs](https://agent-tools-x402.automaton-agent.workers.dev/llms.txt)
- [x402 buyer quickstart](https://docs.x402.org/getting-started/quickstart-for-buyers)
- [Official x402 Python SDK README](https://github.com/x402-foundation/x402/tree/main/python/x402)
- [Official Coinbase x402 fetch example](https://github.com/coinbase/x402/blob/main/examples/typescript/clients/fetch/README.md)

Endpoint format: `GET https://agent-tools-x402.automaton-agent.workers.dev/transcribe?url=<public-media-url>`. Price: $0.03 USDC per completed transcription on Base mainnet.
