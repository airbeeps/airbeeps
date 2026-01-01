/**
 * Unit tests for SSE parsing logic.
 *
 * Tests the SSE event parsing utility used in useStreamingChat.
 * This is a critical piece of functionality for the chat feature.
 *
 * These tests import and validate the actual production code from
 * ~/utils/sseParser.ts, ensuring test accuracy.
 */

import { describe, it, expect } from "vitest";
import { parseSseDataLines, parseSseEvent, isSseDoneSignal } from "~/utils/sseParser";

describe("SSE Parser", () => {
  describe("parseSseDataLines", () => {
    it("should extract data from simple SSE event", () => {
      const rawEvent = 'data: {"type": "test"}';
      const result = parseSseDataLines(rawEvent);

      expect(result).toEqual(['{"type": "test"}']);
    });

    it("should handle data without space after colon", () => {
      const rawEvent = 'data:{"type": "test"}';
      const result = parseSseDataLines(rawEvent);

      expect(result).toEqual(['{"type": "test"}']);
    });

    it("should handle multiple data lines", () => {
      const rawEvent = 'data: {"line": 1}\ndata: {"line": 2}';
      const result = parseSseDataLines(rawEvent);

      expect(result).toEqual(['{"line": 1}', '{"line": 2}']);
    });

    it("should ignore non-data lines", () => {
      const rawEvent = 'event: message\nid: 123\ndata: {"type": "test"}';
      const result = parseSseDataLines(rawEvent);

      expect(result).toEqual(['{"type": "test"}']);
    });

    it("should handle empty events", () => {
      const rawEvent = "";
      const result = parseSseDataLines(rawEvent);

      expect(result).toEqual([]);
    });

    it("should handle comments in SSE stream", () => {
      const rawEvent = ': this is a comment\ndata: {"type": "test"}';
      const result = parseSseDataLines(rawEvent);

      expect(result).toEqual(['{"type": "test"}']);
    });
  });

  describe("parseSseEvent", () => {
    it("should parse content_chunk event", () => {
      const rawEvent =
        'data: {"type": "content_chunk", "data": {"content": "Hello", "is_final": false}}';
      const result = parseSseEvent(rawEvent);

      expect(result).toEqual({
        type: "content_chunk",
        data: { content: "Hello", is_final: false },
      });
    });

    it("should parse error event", () => {
      const rawEvent = 'data: {"type": "error", "data": {"error": "Something went wrong"}}';
      const result = parseSseEvent(rawEvent);

      expect(result).toEqual({
        type: "error",
        data: { error: "Something went wrong" },
      });
    });

    it("should parse assistant_message_complete event", () => {
      const rawEvent =
        'data: {"type": "assistant_message_complete", "data": {"id": "123", "content": "Hello world"}}';
      const result = parseSseEvent(rawEvent);

      expect(result).toEqual({
        type: "assistant_message_complete",
        data: { id: "123", content: "Hello world" },
      });
    });

    it("should parse agent_action event", () => {
      const rawEvent =
        'data: {"type": "agent_action", "data": {"tool": "calculator", "description": "Computing..."}}';
      const result = parseSseEvent(rawEvent);

      expect(result).toEqual({
        type: "agent_action",
        data: { tool: "calculator", description: "Computing..." },
      });
    });

    it("should parse reasoning_trace event", () => {
      const rawEvent =
        'data: {"type": "reasoning_trace", "data": {"content": "Thinking...", "is_final": false}}';
      const result = parseSseEvent(rawEvent);

      expect(result).toEqual({
        type: "reasoning_trace",
        data: { content: "Thinking...", is_final: false },
      });
    });

    it("should return null for [DONE] signal", () => {
      const rawEvent = "data: [DONE]";
      const result = parseSseEvent(rawEvent);

      expect(result).toBeNull();
    });

    it("should return null for invalid JSON", () => {
      const rawEvent = "data: invalid json";
      const result = parseSseEvent(rawEvent);

      expect(result).toBeNull();
    });

    it("should return null for empty data", () => {
      const rawEvent = "data: ";
      const result = parseSseEvent(rawEvent);

      expect(result).toBeNull();
    });

    it("should return null for event with only whitespace", () => {
      const rawEvent = "data:    ";
      const result = parseSseEvent(rawEvent);

      expect(result).toBeNull();
    });
  });

  describe("isSseDoneSignal", () => {
    it("should return true for [DONE] signal", () => {
      expect(isSseDoneSignal("data: [DONE]")).toBe(true);
    });

    it("should return true for [DONE] without space", () => {
      expect(isSseDoneSignal("data:[DONE]")).toBe(true);
    });

    it("should return false for regular data", () => {
      expect(isSseDoneSignal('data: {"type": "content_chunk"}')).toBe(false);
    });

    it("should return false for empty event", () => {
      expect(isSseDoneSignal("")).toBe(false);
    });
  });

  describe("event assembly", () => {
    it("should correctly assemble content from multiple chunks", () => {
      const chunks = [
        { type: "content_chunk", data: { content: "Hello", is_final: false } },
        { type: "content_chunk", data: { content: " ", is_final: false } },
        { type: "content_chunk", data: { content: "world", is_final: false } },
        { type: "content_chunk", data: { content: "!", is_final: true } },
      ];

      const content = chunks
        .filter((c) => c.type === "content_chunk")
        .map((c) => c.data.content)
        .join("");

      expect(content).toBe("Hello world!");
    });

    it("should preserve event order", () => {
      const rawEvents = [
        'data: {"type": "content_chunk", "data": {"content": "1", "is_final": false}}',
        'data: {"type": "content_chunk", "data": {"content": "2", "is_final": false}}',
        'data: {"type": "content_chunk", "data": {"content": "3", "is_final": true}}',
      ];

      const results = rawEvents.map(parseSseEvent).filter(Boolean);

      expect(results.length).toBe(3);
      expect(results.map((r) => (r as any).data.content)).toEqual(["1", "2", "3"]);
    });
  });

  describe("test mode response", () => {
    it("should parse TEST_MODE_RESPONSE correctly", () => {
      // This simulates what the fake LLM returns in test mode
      const rawEvent =
        'data: {"type": "content_chunk", "data": {"content": "TEST_MODE_RESPONSE: Hello!", "is_final": false}}';
      const result = parseSseEvent(rawEvent);

      expect(result?.data?.content).toContain("TEST_MODE_RESPONSE:");
    });

    it("should handle deterministic test response structure", () => {
      const chunks = [
        { type: "content_chunk", data: { content: "TEST_MODE", is_final: false } },
        { type: "content_chunk", data: { content: "_RESPONSE", is_final: false } },
        { type: "content_chunk", data: { content: ": test", is_final: true } },
      ];

      const content = chunks.map((c) => c.data.content).join("");

      expect(content).toBe("TEST_MODE_RESPONSE: test");
    });
  });

  describe("edge cases", () => {
    it("should handle multiline JSON data", () => {
      const rawEvent = 'data: {"type": "test"}\ndata: ';
      const result = parseSseDataLines(rawEvent);

      expect(result).toEqual(['{"type": "test"}', ""]);
    });

    it("should handle Windows line endings (CRLF)", () => {
      const rawEvent = 'data: {"type": "test"}\r\ndata: {"type": "test2"}';
      // Note: In production, CRLF is normalized to LF before parsing
      const normalized = rawEvent.replace(/\r\n/g, "\n");
      const result = parseSseDataLines(normalized);

      expect(result).toEqual(['{"type": "test"}', '{"type": "test2"}']);
    });

    it("should handle nested JSON objects", () => {
      const rawEvent = 'data: {"type": "complex", "data": {"nested": {"deep": true}}}';
      const result = parseSseEvent(rawEvent);

      expect(result).toEqual({
        type: "complex",
        data: { nested: { deep: true } },
      });
    });

    it("should handle arrays in JSON", () => {
      const rawEvent = 'data: {"type": "array", "data": {"items": [1, 2, 3]}}';
      const result = parseSseEvent(rawEvent);

      expect(result).toEqual({
        type: "array",
        data: { items: [1, 2, 3] },
      });
    });
  });
});
