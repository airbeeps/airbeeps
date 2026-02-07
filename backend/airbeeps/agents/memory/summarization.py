"""
Memory Summarization Service.

Provides LLM-based summarization of memories for compaction.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default summarization prompt
SUMMARIZATION_PROMPT = """Summarize the following memories into a concise summary that preserves the key information.
Focus on:
- Important facts and preferences
- Key decisions or events
- Recurring patterns or themes

Memories to summarize:
{memories}

Provide a clear, concise summary that captures the essential information:"""

CONVERSATION_SUMMARY_PROMPT = """Create a summary of this conversation that captures:
- The main topics discussed
- Key decisions or conclusions reached
- Important context for future conversations

Conversation:
{conversation}

Summary:"""


class MemorySummarizer:
    """
    Service for summarizing memories using LLM.
    """

    def __init__(self, llm_client: Any = None):
        """
        Initialize summarizer.

        Args:
            llm_client: LiteLLM-compatible client for summarization
        """
        self._llm_client = llm_client

    async def summarize_memories(
        self,
        memories: list[dict[str, Any]],
        max_length: int = 500,
        model: str = "gpt-4o-mini",
    ) -> str:
        """
        Summarize multiple memories into a single summary.

        Args:
            memories: List of memory dicts with 'content' field
            max_length: Maximum length of summary
            model: Model to use for summarization

        Returns:
            Summarized content
        """
        if not memories:
            return ""

        if len(memories) == 1:
            return memories[0].get("content", "")

        # Format memories for the prompt
        memory_text = "\n\n".join(
            f"[{m.get('type', 'UNKNOWN')}] {m.get('content', '')}" for m in memories
        )

        prompt = SUMMARIZATION_PROMPT.format(memories=memory_text)

        # If no LLM client, use simple truncation
        if self._llm_client is None:
            return self._simple_summarize(memories, max_length)

        try:
            from litellm import acompletion

            response = await acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_length,
                temperature=0.3,
            )

            summary = response.choices[0].message.content
            return (
                summary.strip()
                if summary
                else self._simple_summarize(memories, max_length)
            )

        except Exception as e:
            logger.warning(f"LLM summarization failed, using simple: {e}")
            return self._simple_summarize(memories, max_length)

    async def summarize_conversation(
        self,
        messages: list[dict[str, Any]],
        max_length: int = 500,
        model: str = "gpt-4o-mini",
    ) -> str:
        """
        Summarize a conversation into a memory.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_length: Maximum length of summary
            model: Model to use for summarization

        Returns:
            Conversation summary
        """
        if not messages:
            return ""

        # Format conversation
        conversation_text = "\n".join(
            f"{m.get('role', 'unknown').upper()}: {m.get('content', '')}"
            for m in messages
        )

        prompt = CONVERSATION_SUMMARY_PROMPT.format(conversation=conversation_text)

        if self._llm_client is None:
            return self._simple_conversation_summary(messages, max_length)

        try:
            from litellm import acompletion

            response = await acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_length,
                temperature=0.3,
            )

            summary = response.choices[0].message.content
            return (
                summary.strip()
                if summary
                else self._simple_conversation_summary(messages, max_length)
            )

        except Exception as e:
            logger.warning(f"LLM conversation summarization failed: {e}")
            return self._simple_conversation_summary(messages, max_length)

    def _simple_summarize(self, memories: list[dict[str, Any]], max_length: int) -> str:
        """Simple non-LLM summarization by truncation and combination."""
        if not memories:
            return ""

        # Combine memories with type prefixes
        combined = []
        remaining_length = max_length

        for m in memories:
            content = m.get("content", "")
            mem_type = m.get("type", "UNKNOWN")

            if remaining_length <= 0:
                break

            # Truncate if needed
            if len(content) > remaining_length:
                content = content[: remaining_length - 3] + "..."

            combined.append(f"[{mem_type}] {content}")
            remaining_length -= len(content) + len(mem_type) + 4

        return " | ".join(combined)

    def _simple_conversation_summary(
        self, messages: list[dict[str, Any]], max_length: int
    ) -> str:
        """Simple non-LLM conversation summary."""
        if not messages:
            return ""

        # Extract key points (first and last messages, plus any with questions)
        summary_parts = []

        if messages:
            first = messages[0]
            summary_parts.append(f"Started with: {first.get('content', '')[:100]}")

        if len(messages) > 1:
            last = messages[-1]
            summary_parts.append(f"Concluded with: {last.get('content', '')[:100]}")

        summary = ". ".join(summary_parts)
        if len(summary) > max_length:
            summary = summary[: max_length - 3] + "..."

        return summary


# Global instance
_summarizer: MemorySummarizer | None = None


def get_memory_summarizer(llm_client: Any = None) -> MemorySummarizer:
    """Get or create memory summarizer instance."""
    global _summarizer
    if _summarizer is None:
        _summarizer = MemorySummarizer(llm_client=llm_client)
    return _summarizer
