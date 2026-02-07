"""
Agent Execution Engine using LiteLLM

This module provides the main agent execution loop with:
- Tool loading (local + MCP)
- Security layer integration
- Native function calling support
- Streaming execution
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.ai_models.client_factory import create_chat_model
from airbeeps.assistants.models import Assistant
from airbeeps.system_config.service import config_service

from .descriptions import (
    get_action_description,
    get_observation_description,
    get_tool_display_name,
)
from .mcp.registry import mcp_registry
from .mcp.tools_adapter import MCPToolAdapter
from .security import ContentFilter, PermissionChecker, InputValidator, OutputValidator
from .tools.base import AgentToolConfig
from .tools.knowledge_base import KnowledgeBaseTool
from .tools.registry import tool_registry

if TYPE_CHECKING:
    from .tools.base import AgentTool

logger = logging.getLogger(__name__)


class AgentExecutionEngine:
    """Agent execution engine using LiteLLM - for Assistant with tools"""

    def __init__(
        self,
        assistant: Assistant,
        session: AsyncSession | None = None,
        system_prompt_override: str | None = None,
        user: Any | None = None,
        enable_security: bool = True,
    ):
        self.assistant = assistant
        self.session = session
        self.system_prompt_override = system_prompt_override
        self.user = user
        self.tools: list[AgentTool] = []
        self.llm = None
        self.max_iterations = assistant.agent_max_iterations or 10

        # Security layer
        self.enable_security = enable_security
        self.permission_checker = PermissionChecker() if enable_security else None
        self.content_filter = ContentFilter() if enable_security else None
        self.input_validator = InputValidator() if enable_security else None
        self.output_validator = OutputValidator() if enable_security else None

        # Track tool usage for this session
        self.tool_call_count = 0
        self.total_cost = 0.0

    async def initialize(self):
        """Initialize agent (load LLM and tools)"""
        self.llm = self._create_llm()
        await self._load_tools()

    def _create_llm(self):
        """Create LLM client using create_chat_model factory"""
        model = self.assistant.model
        provider = model.provider

        return create_chat_model(
            provider=provider,
            model_name=model.name,
            temperature=self.assistant.temperature,
            **self.assistant.config,
        )

    async def _load_tools(self):
        """Load all tools (local and MCP)"""
        # Load local tools
        await self._load_local_tools()

        # Load MCP tools (now enabled with security)
        await self._load_mcp_tools()

    async def _load_local_tools(self):
        """Load local registered tools"""
        for tool_name in self.assistant.agent_enabled_tools:
            try:
                # Build tool config with assistant-specific parameters
                tool_config = AgentToolConfig(
                    enabled=True,
                    parameters=self._get_tool_parameters(tool_name),
                )

                # Special handling for knowledge_base tools
                if tool_name in ["knowledge_base_query", "knowledge_base_search"]:
                    tool_config.parameters["knowledge_base_ids"] = [
                        str(kb_id) for kb_id in self.assistant.knowledge_base_ids
                    ]

                    if tool_name == "knowledge_base_query":
                        tool = KnowledgeBaseTool(
                            config=tool_config, session=self.session
                        )
                    else:
                        from .tools.knowledge_base import KnowledgeBaseSearchTool

                        tool = KnowledgeBaseSearchTool(
                            config=tool_config, session=self.session
                        )
                else:
                    tool = tool_registry.get_tool(tool_name, tool_config)

                # Check permission if security enabled
                if self.enable_security and self.permission_checker:
                    perm_result = await self.permission_checker.can_use_tool(
                        self.user, tool_name, check_quota=False
                    )
                    if not perm_result.allowed:
                        logger.warning(
                            f"Tool {tool_name} not allowed for user: {perm_result.reason}"
                        )
                        continue

                self.tools.append(tool)
                logger.info(f"Loaded local tool: {tool_name}")
            except Exception as e:
                logger.error(f"Failed to load tool {tool_name}: {e}")

    def _get_tool_parameters(self, tool_name: str) -> dict[str, Any]:
        """Get tool-specific parameters from assistant config"""
        tool_configs = self.assistant.agent_tool_config or {}
        return tool_configs.get(tool_name, {})

    async def _load_mcp_tools(self):
        """Load tools from MCP servers with error handling"""
        # Check if assistant has MCP servers configured
        try:
            mcp_servers = self.assistant.mcp_servers
        except Exception:
            # Relationship not loaded
            logger.debug("MCP servers relationship not loaded, skipping")
            return

        for mcp_server in mcp_servers:
            if not mcp_server.is_active:
                continue

            try:
                # Check if server is registered
                if not mcp_registry.is_registered(mcp_server.name):
                    # Register the server
                    await mcp_registry.register_server(mcp_server)

                # Get client
                client = await mcp_registry.get_server(mcp_server.name)

                # Get tools
                mcp_tool_list = await client.list_tools()

                # Convert to agent tools
                for tool_info in mcp_tool_list:
                    adapter = MCPToolAdapter(mcp_client=client, tool_info=tool_info)

                    # Check permission if security enabled
                    if self.enable_security and self.permission_checker:
                        perm_result = await self.permission_checker.can_use_tool(
                            self.user, tool_info["name"], check_quota=False
                        )
                        if not perm_result.allowed:
                            logger.warning(
                                f"MCP tool {tool_info['name']} not allowed: {perm_result.reason}"
                            )
                            continue

                    self.tools.append(adapter)
                    logger.info(
                        f"Loaded MCP tool: {tool_info['name']} from {mcp_server.name}"
                    )

            except Exception as e:
                # Continue with other servers on failure (graceful degradation)
                logger.error(f"Failed to load MCP tools from {mcp_server.name}: {e}")
                continue

    def _build_tools_description(self) -> str:
        """Build tools description for the system prompt"""
        if not self.tools:
            return ""

        tools_desc = ["You have access to the following tools:"]
        for tool in self.tools:
            tools_desc.append(f"\n- {tool.name}: {tool.description}")

        tools_desc.append(
            "\n\nTo use a tool, respond with a JSON object in this format:"
        )
        tools_desc.append(
            '{"tool": "tool_name", "input": {"param1": "value1", "param2": "value2"}}'
        )
        tools_desc.append(
            "\nAfter receiving the tool result, you can use another tool or provide your final answer."
        )
        tools_desc.append(
            "When you have enough information, provide your final answer without using any tool."
        )

        return "\n".join(tools_desc)

    def _build_openai_tools_schema(self) -> list[dict]:
        """Build OpenAI function calling tools schema"""
        tools_schema = []
        for tool in self.tools:
            if hasattr(tool, "to_openai_tool"):
                tools_schema.append(tool.to_openai_tool())
            else:
                # Fallback for tools without schema
                tools_schema.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                )
        return tools_schema

    def _check_provider_supports_function_calling(self) -> bool:
        """Check if the current provider supports native function calling"""
        # Most modern providers support it
        provider = self.assistant.model.provider
        provider_name = (
            provider.name.lower()
            if hasattr(provider, "name")
            else str(provider).lower()
        )

        # Known providers with function calling support
        supported_providers = [
            "openai",
            "azure",
            "anthropic",
            "google",
            "gemini",
            "mistral",
            "groq",
            "together",
            "fireworks",
            "deepseek",
        ]

        for supported in supported_providers:
            if supported in provider_name:
                return True

        return False

    def _build_system_prompt(self) -> str:
        """Build system prompt with tools"""
        base_prompt = (
            self.system_prompt_override
            or self.assistant.system_prompt
            or "You are a helpful AI agent."
        )

        tools_desc = self._build_tools_description()
        if tools_desc:
            return f"{base_prompt}\n\n{tools_desc}"
        return base_prompt

    async def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool with security layer wrapping"""
        # Find the tool
        tool = None
        for t in self.tools:
            if t.name == tool_name:
                tool = t
                break

        if not tool:
            return f"Error: Tool '{tool_name}' not found"

        user_id = (
            str(getattr(self.user, "id", "anonymous")) if self.user else "anonymous"
        )

        # Security Layer 1: Permission check
        if self.enable_security and self.permission_checker:
            perm_result = await self.permission_checker.can_use_tool(
                self.user, tool_name, check_quota=True
            )
            if not perm_result.allowed:
                logger.warning(
                    f"Permission denied for {tool_name}: {perm_result.reason}"
                )
                return f"Error: {perm_result.reason}"

        # Security Layer 2: Input validation
        if self.enable_security and self.input_validator:
            validation_result = self.input_validator.validate(tool_input)
            if not validation_result.valid:
                logger.warning(
                    f"Input validation failed for {tool_name}: {validation_result.errors}"
                )
                return f"Error: Invalid input - {', '.join(validation_result.errors)}"
            tool_input = validation_result.sanitized_data or tool_input

        # Security Layer 3: Content filtering
        if self.enable_security and self.content_filter:
            filter_result = await self.content_filter.filter_input(
                tool_name, tool_input
            )
            if filter_result.action.value == "block":
                logger.warning(
                    f"Input blocked for {tool_name}: {filter_result.warnings}"
                )
                return f"Error: Input blocked - {', '.join(filter_result.warnings)}"
            tool_input = filter_result.modified_content or tool_input

        try:
            # Execute the tool
            result = await tool.execute(**tool_input)

            # Track usage
            self.tool_call_count += 1
            if self.enable_security and self.permission_checker:
                self.permission_checker.record_usage(user_id, tool_name)

            # Security Layer 4: Output filtering
            if self.enable_security and self.content_filter:
                output_filter_result = await self.content_filter.filter_output(
                    tool_name, result
                )
                result = output_filter_result.modified_content or str(result)

                if output_filter_result.warnings:
                    logger.info(
                        f"Output filtered for {tool_name}: {output_filter_result.warnings}"
                    )

            # Security Layer 5: Output validation
            if self.enable_security and self.output_validator:
                output_validation = self.output_validator.validate(result)
                if output_validation.sanitized_data:
                    result = output_validation.sanitized_data

            return str(result)

        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {e}")
            return f"Error executing tool: {e!s}"

    def _parse_tool_call(self, content: str) -> dict[str, Any] | None:
        """Try to parse tool call from LLM response"""
        # Try to find JSON in the content
        content = content.strip()

        # Look for JSON object
        try:
            # Try direct JSON parse
            data = json.loads(content)
            if isinstance(data, dict) and "tool" in data:
                return data
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                try:
                    data = json.loads(content[start:end].strip())
                    if isinstance(data, dict) and "tool" in data:
                        return data
                except json.JSONDecodeError:
                    pass

        # Try to extract JSON object from text
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(content[start:end])
                if isinstance(data, dict) and "tool" in data:
                    return data
            except json.JSONDecodeError:
                pass

        return None

    async def execute(
        self,
        user_input: str,
        conversation_id: Any | None = None,
        chat_history: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Execute agent task"""
        if not self.llm:
            await self.initialize()

        try:
            # Build messages for the agent
            messages = []

            # Add system prompt
            system_prompt = self._build_system_prompt()
            messages.append({"role": "system", "content": system_prompt})

            # Add chat history if available
            if chat_history:
                messages.extend(chat_history)

            # Add current user input
            messages.append({"role": "user", "content": user_input})

            # Execute agent loop
            iteration = 0
            while iteration < self.max_iterations:
                iteration += 1

                # Call LLM
                response = await self.llm.ainvoke(messages)

                # Extract content from response
                if hasattr(response, "choices") and response.choices:
                    assistant_message = response.choices[0].message.content
                else:
                    break

                # Check if this is a tool call
                tool_call = self._parse_tool_call(assistant_message)

                if tool_call:
                    # Execute tool
                    tool_name = tool_call.get("tool")
                    tool_input = tool_call.get("input", {})

                    tool_result = await self._execute_tool(tool_name, tool_input)

                    # Add to messages
                    messages.append({"role": "assistant", "content": assistant_message})
                    messages.append(
                        {"role": "user", "content": f"Tool result: {tool_result}"}
                    )
                else:
                    # This is the final answer
                    return {
                        "output": assistant_message,
                        "iterations": iteration,
                    }

            # Max iterations reached
            return {
                "output": "I apologize, but I've reached the maximum number of steps. Please try rephrasing your question.",
                "iterations": iteration,
            }

        except Exception as e:
            logger.error(f"Agent execution error: {e}")
            raise

    async def stream_execute(
        self,
        user_input: str,
        conversation_id: Any | None = None,
        chat_history: list[dict] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream execute agent task with detailed events

        Yields events:
        - {"type": "agent_action", "data": {"tool": str, "input": dict, "thought": str}}
        - {"type": "agent_observation", "data": {"observation": str}}
        - {"type": "content_chunk", "data": {"content": str, "is_final": bool}}
        """
        if not self.llm:
            await self.initialize()

        try:
            # Match non-agent behavior: optionally use non-streaming calls to capture reasoning,
            # then simulate streaming with small chunks.
            # VERIFIED: LiteLLM streaming does NOT include reasoning - delta only has provider_specific_fields
            # Non-streaming (ainvoke) is required to capture message.reasoning
            use_non_streaming_for_reasoning = True
            try:
                if self.session:
                    use_non_streaming_for_reasoning = (
                        await config_service.get_config_value(
                            self.session, "ui_show_agent_thinking", True
                        )
                    )
            except Exception:
                use_non_streaming_for_reasoning = True

            # Build messages for the agent
            messages = []

            # Add system prompt
            system_prompt = self._build_system_prompt()
            messages.append({"role": "system", "content": system_prompt})

            # Add chat history if available
            if chat_history:
                messages.extend(chat_history)

            # Add current user input
            messages.append({"role": "user", "content": user_input})

            # Track state
            token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            iteration = 0

            while iteration < self.max_iterations:
                iteration += 1

                full_response = ""
                iteration_reasoning_emitted = False

                if use_non_streaming_for_reasoning:
                    # Non-streaming call (captures reasoning metadata on supported providers/models)
                    response = await self.llm.ainvoke(messages)
                    if (
                        not response
                        or not hasattr(response, "choices")
                        or not response.choices
                    ):
                        break

                    # Extract token usage (non-streaming)
                    if hasattr(response, "usage") and response.usage:
                        usage = response.usage
                        if hasattr(usage, "prompt_tokens") and usage.prompt_tokens:
                            token_usage["input_tokens"] += usage.prompt_tokens or 0
                        if (
                            hasattr(usage, "completion_tokens")
                            and usage.completion_tokens
                        ):
                            token_usage["output_tokens"] += usage.completion_tokens or 0
                        if hasattr(usage, "total_tokens") and usage.total_tokens:
                            token_usage["total_tokens"] += usage.total_tokens or 0

                    choice = response.choices[0]
                    message_obj = getattr(choice, "message", None)

                    # Extract reasoning from message object (if provided)
                    reasoning_content = None
                    if message_obj is not None:
                        if hasattr(message_obj, "reasoning") and message_obj.reasoning:
                            reasoning_content = message_obj.reasoning
                        elif (
                            hasattr(message_obj, "reasoning_content")
                            and message_obj.reasoning_content
                        ):
                            reasoning_content = message_obj.reasoning_content
                        elif hasattr(message_obj, "__dict__"):
                            msg_dict = message_obj.__dict__
                            reasoning_content = msg_dict.get(
                                "reasoning"
                            ) or msg_dict.get("reasoning_content")

                    if (
                        reasoning_content
                        and isinstance(reasoning_content, str)
                        and reasoning_content.strip()
                    ):
                        iteration_reasoning_emitted = True
                        chunk_size = 50
                        for i in range(0, len(reasoning_content), chunk_size):
                            yield {
                                "type": "reasoning_trace",
                                "data": {
                                    "content": reasoning_content[i : i + chunk_size],
                                    "is_final": False,
                                },
                            }
                            await asyncio.sleep(0.01)

                    # Extract content from message
                    content = ""
                    if (
                        message_obj is not None
                        and hasattr(message_obj, "content")
                        and message_obj.content
                    ):
                        content = (
                            message_obj.content
                            if isinstance(message_obj.content, str)
                            else str(message_obj.content)
                        )

                    # Fallback: extract <think> blocks from content as reasoning
                    if "<think>" in content:
                        think_match = re.search(
                            r"<think>(.*?)</think>", content, re.DOTALL
                        )
                        if think_match:
                            think_content = (think_match.group(1) or "").strip()
                            if think_content:
                                iteration_reasoning_emitted = True
                                for i in range(0, len(think_content), 50):
                                    yield {
                                        "type": "reasoning_trace",
                                        "data": {
                                            "content": think_content[i : i + 50],
                                            "is_final": False,
                                        },
                                    }
                                    await asyncio.sleep(0.01)
                        # Remove think blocks from content shown to user
                        content = re.sub(
                            r"<think>.*?</think>", "", content, flags=re.DOTALL
                        ).strip()

                    full_response = content

                    # Check if this is a tool call (internal)
                    tool_call = self._parse_tool_call(full_response)
                    if tool_call:
                        tool_name = tool_call.get("tool")
                        tool_input = tool_call.get("input", {})

                        description = get_action_description(tool_name, tool_input)
                        display_name = get_tool_display_name(tool_name)

                        yield {
                            "type": "agent_action",
                            "data": {
                                "tool": tool_name,
                                "tool_display_name": display_name,
                                "input": tool_input,
                                "thought": "",
                                "description": description,
                            },
                        }

                        tool_result = await self._execute_tool(tool_name, tool_input)
                        description = get_observation_description(
                            tool_name, tool_result
                        )

                        yield {
                            "type": "agent_observation",
                            "data": {
                                "tool": tool_name,
                                "tool_display_name": display_name,
                                "observation": tool_result,
                                "description": description,
                            },
                        }

                        # Finalize reasoning chunk for this iteration (if any)
                        if iteration_reasoning_emitted:
                            yield {
                                "type": "reasoning_trace",
                                "data": {"content": "", "is_final": True},
                            }

                        # Add to messages for next iteration
                        messages.append({"role": "assistant", "content": full_response})
                        messages.append(
                            {"role": "user", "content": f"Tool result: {tool_result}"}
                        )
                        continue

                    # Final answer: simulate streaming for content
                    if full_response:
                        chunk_size = 20
                        for i in range(0, len(full_response), chunk_size):
                            yield {
                                "type": "content_chunk",
                                "data": {
                                    "content": full_response[i : i + chunk_size],
                                    "is_final": False,
                                },
                            }
                            await asyncio.sleep(0.01)

                    # Final markers
                    yield {
                        "type": "content_chunk",
                        "data": {"content": "", "is_final": True},
                    }
                    if iteration_reasoning_emitted:
                        yield {
                            "type": "reasoning_trace",
                            "data": {"content": "", "is_final": True},
                        }

                    if token_usage["total_tokens"] > 0:
                        yield {"type": "token_usage", "data": token_usage}
                    return

                # Streaming mode (fallback when reasoning display is disabled)
                # NOTE: Verified that LiteLLM streaming does NOT include reasoning content
                # delta.__dict__ only contains {'provider_specific_fields': None}
                last_chunk = None
                async for chunk in self.llm.astream(messages):
                    if not chunk or not hasattr(chunk, "choices") or not chunk.choices:
                        continue

                    last_chunk = chunk
                    delta = chunk.choices[0].delta

                    # Extract token usage
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage = chunk.usage
                        if hasattr(usage, "prompt_tokens"):
                            token_usage["input_tokens"] += usage.prompt_tokens or 0
                        if hasattr(usage, "completion_tokens"):
                            token_usage["output_tokens"] += usage.completion_tokens or 0
                        if hasattr(usage, "total_tokens"):
                            token_usage["total_tokens"] += usage.total_tokens or 0

                    # Extract reasoning (for models like DeepSeek-R1, o1, o3)
                    reasoning_text = None
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                        reasoning_text = delta.reasoning_content
                    elif hasattr(delta, "reasoning") and delta.reasoning:
                        reasoning_text = delta.reasoning
                    elif hasattr(delta, "__dict__"):
                        delta_dict = delta.__dict__
                        reasoning_text = delta_dict.get(
                            "reasoning_content"
                        ) or delta_dict.get("reasoning")

                    if (
                        reasoning_text
                        and isinstance(reasoning_text, str)
                        and reasoning_text.strip()
                    ):
                        iteration_reasoning_emitted = True
                        yield {
                            "type": "reasoning_trace",
                            "data": {"content": reasoning_text, "is_final": False},
                        }

                    # Extract content
                    if hasattr(delta, "content") and delta.content:
                        content = delta.content
                        full_response += content
                        yield {
                            "type": "content_chunk",
                            "data": {"content": content, "is_final": False},
                        }

                # Check final chunk for reasoning (some models only provide at end)
                if last_chunk and hasattr(last_chunk, "choices") and last_chunk.choices:
                    choice = last_chunk.choices[0]
                    if hasattr(choice, "message") and choice.message:
                        msg = choice.message
                        final_reasoning = None
                        if hasattr(msg, "reasoning_content") and msg.reasoning_content:
                            final_reasoning = msg.reasoning_content
                        elif hasattr(msg, "reasoning") and msg.reasoning:
                            final_reasoning = msg.reasoning
                        elif hasattr(msg, "__dict__"):
                            msg_dict = msg.__dict__
                            final_reasoning = msg_dict.get(
                                "reasoning_content"
                            ) or msg_dict.get("reasoning")

                        if (
                            final_reasoning
                            and isinstance(final_reasoning, str)
                            and final_reasoning.strip()
                        ):
                            iteration_reasoning_emitted = True
                            yield {
                                "type": "reasoning_trace",
                                "data": {"content": final_reasoning, "is_final": False},
                            }

                if iteration_reasoning_emitted:
                    yield {
                        "type": "reasoning_trace",
                        "data": {"content": "", "is_final": True},
                    }

                # Check if this is a tool call
                tool_call = self._parse_tool_call(full_response)

                if tool_call:
                    # This is a tool call
                    tool_name = tool_call.get("tool")
                    tool_input = tool_call.get("input", {})

                    description = get_action_description(tool_name, tool_input)
                    display_name = get_tool_display_name(tool_name)

                    # Yield agent action
                    yield {
                        "type": "agent_action",
                        "data": {
                            "tool": tool_name,
                            "tool_display_name": display_name,
                            "input": tool_input,
                            "thought": "",
                            "description": description,
                        },
                    }

                    # Execute tool
                    tool_result = await self._execute_tool(tool_name, tool_input)

                    description = get_observation_description(tool_name, tool_result)

                    # Yield observation
                    yield {
                        "type": "agent_observation",
                        "data": {
                            "tool": tool_name,
                            "tool_display_name": display_name,
                            "observation": tool_result,
                            "description": description,
                        },
                    }

                    # Add to messages for next iteration
                    messages.append({"role": "assistant", "content": full_response})
                    messages.append(
                        {"role": "user", "content": f"Tool result: {tool_result}"}
                    )
                else:
                    # This is the final answer
                    yield {
                        "type": "content_chunk",
                        "data": {"content": "", "is_final": True},
                    }

                    # Send token usage
                    if token_usage["total_tokens"] > 0:
                        yield {"type": "token_usage", "data": token_usage}

                    return

            # Max iterations reached
            yield {
                "type": "content_chunk",
                "data": {
                    "content": "\n\nI've reached the maximum number of steps. Please try rephrasing your question.",
                    "is_final": False,
                },
            }
            yield {
                "type": "content_chunk",
                "data": {"content": "", "is_final": True},
            }

            if token_usage["total_tokens"] > 0:
                yield {"type": "token_usage", "data": token_usage}

        except Exception as e:
            logger.error(f"Agent streaming error: {e}")
            logger.error(f"User input: {user_input[:100]}...")  # Log first 100 chars
            logger.error(
                f"Assistant: {self.assistant.name}, Model: {self.assistant.model.name}"
            )
            raise
