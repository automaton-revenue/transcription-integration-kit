import { describe, expect, it, vi } from "vitest";
import { ENDPOINT, parseArgs, transcribe, validateAudioUrl } from "./transcribe.js";

describe("Node transcription client", () => {
  it("shows help without requiring a URL or private key", () => {
    expect(parseArgs(["--help"])).toEqual({ help: true });
  });

  it("rejects non-HTTP URLs and embedded credentials", () => {
    expect(() => validateAudioUrl("file:///tmp/audio.mp3")).toThrow(/absolute http\(s\) URL/);
    expect(() => validateAudioUrl("https://user:secret@example.com/audio.mp3")).toThrow(/credentials/);
  });

  it("sends the audio URL and returns transcript after a mocked paid flow", async () => {
    const mockFetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ x402Version: 2, accepts: [{ scheme: "exact", network: "eip155:8453" }] }), { status: 402 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ text: "hello from audio", language: "en" }), { status: 200 }));
    // Models wrapFetchWithPayment's observable contract: detect 402, retry with
    // payment handling, and return the successful API response. No wallet/network call.
    const mockPaymentFetch = async (request) => {
      const first = await mockFetch(request);
      if (first.status !== 402) return first;
      return mockFetch(request, { headers: { "PAYMENT-SIGNATURE": "mock-x402-signature" } });
    };

    const result = await transcribe("https://example.com/audio.mp3", mockPaymentFetch);
    expect(result.text).toBe("hello from audio");
    expect(mockFetch).toHaveBeenCalledTimes(2);
    const requestUrl = new URL(mockFetch.mock.calls[0][0]);
    expect(requestUrl.origin + requestUrl.pathname).toBe(ENDPOINT);
    expect(requestUrl.searchParams.get("url")).toBe("https://example.com/audio.mp3");
  });

  it("reports API errors rather than treating them as transcripts", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("bad request", { status: 400 }));
    await expect(transcribe("https://example.com/audio.mp3", fetcher)).rejects.toThrow("HTTP 400: bad request");
  });
});
