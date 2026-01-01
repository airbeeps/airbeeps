import type { Message } from "~/types/api";
import { parseSseDataLines, isSseDoneSignal } from "~/utils/sseParser";

export interface AgentStep {
  type: "agent_action" | "agent_observation" | "agent_thought";
  tool?: string;
  tool_display_name?: string;
  observation?: string;
  description?: string;
  thought?: string;
  timestamp?: number;
}

export interface StreamMediaItem {
  id?: string;
  type: string;
  mime_type: string;
  data_url?: string;
  url?: string;
  alt?: string;
  index?: number;
  source?: string;
}

export interface ContentChunkPayload {
  content: string;
  is_final: boolean;
  media?: StreamMediaItem[];
}

export interface ReasoningTracePayload {
  content: string;
  is_final: boolean;
}

export interface ImageAttachment {
  id: string;
  url?: string;
  alt?: string;
  mimeType?: string;
  size?: number;
  fileKey?: string;
}

const serializeImagePayload = (images?: ImageAttachment[]) => {
  if (!images || images.length === 0) {
    return undefined;
  }

  const payload = images
    .map((img) => {
      const normalized: Record<string, any> = {};
      if (img.url) {
        normalized.url = img.url;
      }
      if (!normalized.url) {
        return null;
      }

      if (img.alt) {
        normalized.alt = img.alt;
      }
      if (img.mimeType) {
        normalized.mime_type = img.mimeType;
      }
      if (typeof img.size === "number") {
        normalized.size = img.size;
      }
      if (img.fileKey) {
        normalized.file_key = img.fileKey;
      }

      normalized.id = img.id;
      return normalized;
    })
    .filter(Boolean);

  return payload.length ? payload : undefined;
};

export function useStreamingChat() {
  const { $api } = useNuxtApp();
  const { t, locale } = useI18n();

  const sendStreamingMessage = async (
    content: string,
    conversationId?: string,
    onChunk?: (chunk: ContentChunkPayload) => void,
    onComplete?: (finalMessage: Message) => void,
    onError?: (error: string) => void,
    onAgentStep?: (step: AgentStep) => void,
    onReasoningTrace?: (trace: ReasoningTracePayload) => void,
    images?: ImageAttachment[]
  ) => {
    try {
      const requestBody: any = {
        content,
        language: locale.value,
        ...(conversationId && { conversation_id: conversationId }),
      };

      // Add images if provided
      const serializedImages = serializeImagePayload(images);
      if (serializedImages) {
        requestBody.images = serializedImages;
      }

      // console.log('Sending request to /v1/chat with body:', requestBody)

      // Make a POST request to the SSE endpoint
      const response = await $api<ReadableStream>("/v1/chat", {
        method: "POST",
        body: requestBody,
        responseType: "stream",
      });

      if (!response || typeof response.pipeThrough !== "function") {
        throw new Error("Streaming not supported, falling back to sync mode");
      }

      // Create a new ReadableStream from the response with TextDecoderStream to get the data as text
      const reader = response.pipeThrough(new TextDecoderStream()).getReader();

      let buffer = "";
      const handlers = { onChunk, onComplete, onError, onAgentStep, onReasoningTrace };

      // Read the chunk of data as we get it
      while (true) {
        const { value, done } = await reader.read();

        if (done) {
          // Process any remaining buffered event
          if (buffer.trim().length > 0) {
            const shouldStop = await processSseEvent(buffer, handlers);
            if (shouldStop) {
              return;
            }
          }
          break;
        }

        buffer += value;

        // Normalize line endings for consistent parsing
        buffer = buffer.replace(/\r\n/g, "\n");

        let eventEndIndex;
        while ((eventEndIndex = buffer.indexOf("\n\n")) !== -1) {
          const rawEvent = buffer.slice(0, eventEndIndex);
          buffer = buffer.slice(eventEndIndex + 2);
          const shouldStop = await processSseEvent(rawEvent, handlers);
          if (shouldStop) {
            return;
          }
        }
      }
    } catch (error: any) {
      // Streaming error - handle gracefully

      // Check for 403 Forbidden error (assistant not available)
      if (error?.statusCode === 403 || error?.response?.status === 403) {
        const errorDetail = error?.data?.detail || error?.response?.data?.detail;
        const errorType = errorDetail?.error || "Assistant is not available";
        const assistantStatus = errorDetail?.assistant_status;

        // Create error message
        let errorMsg = t("chat.assistantNotAvailable");
        if (assistantStatus) {
          errorMsg = `${errorMsg} (${t("chat.assistantStatus")}: ${assistantStatus})`;
        }

        onError?.(errorMsg);
        return;
      }

      // Provide more detailed error messages
      let errorMessage = t("chat.unknownError");
      if (error instanceof TypeError && error.message.includes("fetch")) {
        errorMessage = t("chat.networkError");
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }

      // Fallback to sync mode if streaming fails
      try {
        const result = await sendSyncMessage(content, conversationId);
        if (onComplete) {
          onComplete(result.message);
        }
      } catch (syncError: any) {
        // Check for 403 error in sync mode
        if (syncError?.statusCode === 403 || syncError?.response?.status === 403) {
          const errorDetail = syncError?.data?.detail || syncError?.response?.data?.detail;
          const assistantStatus = errorDetail?.assistant_status;

          let errorMsg = t("chat.assistantNotAvailable");
          if (assistantStatus) {
            errorMsg = `${errorMsg} (${t("chat.assistantStatus")}: ${assistantStatus})`;
          }

          onError?.(errorMsg);
          return;
        }

        const syncErrorMessage =
          syncError instanceof Error ? syncError.message : t("chat.sendFailed");
        onError?.(syncErrorMessage);
      }
    }
  };

  const sendSyncMessage = async (content: string, conversationId?: string) => {
    const requestBody = {
      content,
      language: locale.value,
      ...(conversationId && { conversation_id: conversationId }),
    };

    const response = await $api<any>("/v1/chat/sync", {
      method: "POST",
      body: requestBody,
    });

    return response;
  };

  return {
    sendStreamingMessage,
    sendSyncMessage,
  };
}

async function processSseEvent(
  rawEvent: string,
  handlers?: {
    onChunk?: (chunk: ContentChunkPayload) => void;
    onComplete?: (finalMessage: Message) => void;
    onError?: (error: string) => void;
    onAgentStep?: (step: AgentStep) => void;
    onReasoningTrace?: (trace: ReasoningTracePayload) => void;
  }
): Promise<boolean> {
  // Use shared SSE parsing utilities
  const dataLines = parseSseDataLines(rawEvent);

  if (dataLines.length === 0) {
    return false;
  }

  const data = dataLines.join("\n").trim();

  if (!data) {
    return false;
  }

  if (isSseDoneSignal(rawEvent)) {
    return true;
  }

  try {
    const parsed = JSON.parse(data);

    if (parsed.type === "error") {
      handlers?.onError?.(parsed.data?.error || "Unknown error occurred");
      return true;
    }

    if (parsed.type === "content_chunk" && parsed.data) {
      handlers?.onChunk?.(parsed.data);
    }

    if (parsed.type === "reasoning_trace" && parsed.data && handlers?.onReasoningTrace) {
      handlers.onReasoningTrace(parsed.data);
    }

    // Handle batch reasoning traces (sent at end of streaming)
    if (parsed.type === "reasoning_traces" && parsed.data?.traces && handlers?.onReasoningTrace) {
      for (const trace of parsed.data.traces) {
        if (trace.thought) {
          // Convert to ReasoningTracePayload format
          handlers.onReasoningTrace({ content: trace.thought, is_final: false });
        }
      }
      // Send final marker
      handlers.onReasoningTrace({ content: "", is_final: true });
    }

    if (
      (parsed.type === "agent_action" || parsed.type === "agent_observation") &&
      handlers?.onAgentStep
    ) {
      const step: AgentStep = {
        type: parsed.type,
        tool: parsed.data?.tool,
        tool_display_name: parsed.data?.tool_display_name,
        observation: parsed.data?.observation,
        description: parsed.data?.description,
        timestamp: Date.now(),
      };
      handlers.onAgentStep(step);
    }

    if (parsed.type === "assistant_message_complete" && parsed.data) {
      handlers?.onComplete?.(parsed.data);
      return true;
    }
  } catch (err) {
    // Ignore parse errors for SSE chunks
  }

  return false;
}
