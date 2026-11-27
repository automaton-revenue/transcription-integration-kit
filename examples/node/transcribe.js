#!/usr/bin/env node
import { x402Client, wrapFetchWithPayment } from "@x402/fetch";
import { ExactEvmScheme } from "@x402/evm/exact/client";
import { privateKeyToAccount } from "viem/accounts";

export const ENDPOINT = "https://agent-tools-x402.automaton-agent.workers.dev/transcribe";

export function parseArgs(argv) {
  const args = [...argv];
  if (args.includes("--help") || args.includes("-h")) return { help: true };
  let url;
  let privateKey;
  for (let i = 0; i < args.length; i += 1) {
    if (args[i] === "--private-key") {
      privateKey = args[i + 1];
      if (!privateKey || privateKey.startsWith("--")) throw new Error("--private-key requires a value");
      i += 1;
    } else if (args[i].startsWith("--")) {
      throw new Error(`Unknown option: ${args[i]}`);
    } else if (url === undefined) {
      url = args[i];
    } else {
      throw new Error("Only one audio URL may be provided");
    }
  }
  if (!url) throw new Error("Audio URL is required");
  return { url, privateKey };
}

export function validateAudioUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("Audio URL must be an absolute http(s) URL");
  }
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password) {
    throw new Error("Audio URL must be an absolute http(s) URL without embedded credentials");
  }
  return parsed.toString();
}

export function createPaymentFetch(privateKey, baseFetch = fetch) {
  if (!privateKey) throw new Error("Set EVM_PRIVATE_KEY or pass --private-key to pay the x402 challenge");
  const client = new x402Client();
  client.register("eip155:8453", new ExactEvmScheme(privateKeyToAccount(privateKey)));
  return wrapFetchWithPayment(baseFetch, client);
}

export async function transcribe(audioUrl, fetchWithPayment) {
  const validUrl = validateAudioUrl(audioUrl);
  if (typeof fetchWithPayment !== "function") throw new Error("A payment-enabled fetch function is required");
  const endpoint = new URL(ENDPOINT);
  endpoint.searchParams.set("url", validUrl);

  let response;
  try {
    response = await fetchWithPayment(endpoint);
  } catch (error) {
    throw new Error(`Request to transcription API failed: ${error instanceof Error ? error.message : String(error)}`, { cause: error });
  }
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Transcription API returned HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
  }
  let result;
  try {
    result = await response.json();
  } catch (error) {
    throw new Error("Transcription API returned invalid JSON", { cause: error });
  }
  if (!result || typeof result.text !== "string") {
    throw new Error("Transcription API response did not include transcript text");
  }
  return result;
}

function usage() {
  return `Usage: node transcribe.js <audio-url> [--private-key <key>]\n\nTranscribe a public audio/video URL through the x402 API.\nPayment: $0.03 USDC on Base for a successful transcription.\nSet EVM_PRIVATE_KEY in the environment (recommended), or pass --private-key.\nThe wallet key is used locally to authorize payment; never share or commit it.`;
}

async function main(argv) {
  try {
    const parsed = parseArgs(argv);
    if (parsed.help) {
      console.log(usage());
      return 0;
    }
    const key = parsed.privateKey ?? process.env.EVM_PRIVATE_KEY;
    const fetchWithPayment = createPaymentFetch(key);
    const result = await transcribe(parsed.url, fetchWithPayment);
    console.log(result.text);
    return 0;
  } catch (error) {
    console.error(`Error: ${error instanceof Error ? error.message : String(error)}`);
    return 1;
  }
}

const isDirectExecution = process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href;
if (isDirectExecution) process.exitCode = await main(process.argv.slice(2));
