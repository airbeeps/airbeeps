/**
 * SSE (Server-Sent Events) parsing utilities.
 *
 * These functions handle parsing of SSE events from the chat streaming API.
 * Used by useStreamingChat composable and can be tested in isolation.
 */

export interface ParsedSseEvent {
  type: string;
  data?: Record<string, unknown>;
}

/**
 * Parse SSE data line(s) from raw event string.
 *
 * Extracts all "data:" lines from an SSE event, handling both
 * "data: content" (with space) and "data:content" (without space) formats.
 *
 * @param rawEvent - Raw SSE event string (may contain multiple lines)
 * @returns Array of data line contents (without "data:" prefix)
 */
export function parseSseDataLines(rawEvent: string): string[] {
  const lines = rawEvent.split("\n");
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line.startsWith("data:")) {
      continue;
    }
    let content = line.slice(5); // remove "data:"
    if (content.startsWith(" ")) {
      content = content.slice(1);
    }
    dataLines.push(content);
  }

  return dataLines;
}

/**
 * Parse a single SSE event and return the typed result.
 *
 * Combines data lines, handles [DONE] signal, and parses JSON.
 *
 * @param rawEvent - Raw SSE event string
 * @returns Parsed event object with type and data, or null if invalid/done
 */
export function parseSseEvent(rawEvent: string): ParsedSseEvent | null {
  const dataLines = parseSseDataLines(rawEvent);

  if (dataLines.length === 0) {
    return null;
  }

  const data = dataLines.join("\n").trim();

  if (!data || data === "[DONE]") {
    return null;
  }

  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
}

/**
 * Check if the raw event represents the [DONE] signal.
 *
 * @param rawEvent - Raw SSE event string
 * @returns true if this is the [DONE] signal
 */
export function isSseDoneSignal(rawEvent: string): boolean {
  const dataLines = parseSseDataLines(rawEvent);
  if (dataLines.length === 0) {
    return false;
  }
  const data = dataLines.join("\n").trim();
  return data === "[DONE]";
}
