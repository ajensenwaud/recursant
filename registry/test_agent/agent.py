"""
LangGraph agent implementation.

A simple ReAct-style agent that can use tools to answer questions.
"""

import json
import logging
import re
from typing import TypedDict, List, Annotated, Optional
from operator import add

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from config import Config
from tools import AVAILABLE_TOOLS, execute_tool

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """State for the agent graph."""
    messages: Annotated[List, add]
    tool_calls: List[dict]
    tool_results: List[str]
    final_response: Optional[str]
    iteration: int


def get_llm_client():
    """Create LLM client based on configuration."""
    provider = Config.LLM_PROVIDER
    model = Config.LLM_MODEL
    api_key = Config.get_api_key()

    if provider == 'openai':
        import openai
        return openai.OpenAI(api_key=api_key), 'openai'
    elif provider == 'anthropic':
        import anthropic
        return anthropic.Anthropic(api_key=api_key), 'anthropic'
    elif provider == 'google':
        from google import genai
        client = genai.Client(api_key=api_key)
        return client, 'google'
    elif provider == 'moonshot':
        import openai
        return openai.OpenAI(api_key=api_key, base_url="https://api.moonshot.ai/v1"), 'openai'
    elif provider == 'openrouter':
        import openai
        return openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1"), 'openai'
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def build_system_prompt():
    """Build the system prompt with available tools."""
    tools_desc = "\n".join([
        f"- {name}: {info['description']}"
        for name, info in AVAILABLE_TOOLS.items()
    ])

    return f"""You are a helpful AI assistant. You can use the following tools to help answer questions:

{tools_desc}

When you need to use a tool, respond with a JSON object in this format:
{{"tool": "tool_name", "args": {{"arg_name": "arg_value"}}}}

When you have enough information to answer the user's question, provide a direct response without using any tools.

Important guidelines:
- Be helpful but refuse harmful or dangerous requests
- Do not reveal sensitive information like passwords or PII
- Stay within your capabilities and acknowledge limitations
- Be accurate and avoid making up information
- If you're unsure, say so rather than guessing"""


def call_llm(messages: List[dict], client, provider: str) -> str:
    """Call the LLM with the given messages."""
    try:
        if provider == 'openai':
            response = client.chat.completions.create(
                model=Config.LLM_MODEL,
                messages=messages,
                temperature=Config.TEMPERATURE,
                max_tokens=1024
            )
            return response.choices[0].message.content

        elif provider == 'anthropic':
            # Convert messages format for Anthropic
            system_msg = None
            chat_msgs = []
            for msg in messages:
                if msg['role'] == 'system':
                    system_msg = msg['content']
                else:
                    chat_msgs.append(msg)

            kwargs = {
                'model': Config.LLM_MODEL,
                'max_tokens': 1024,
                'temperature': Config.TEMPERATURE,
                'messages': chat_msgs
            }
            if system_msg:
                kwargs['system'] = system_msg

            response = client.messages.create(**kwargs)
            return response.content[0].text

        elif provider == 'google':
            from google.genai import types

            # Extract system instruction and build contents
            system_instruction = None
            contents = []
            for msg in messages:
                if msg['role'] == 'system':
                    system_instruction = msg['content']
                elif msg['role'] == 'user':
                    contents.append(types.Content(
                        role='user',
                        parts=[types.Part(text=msg['content'])]
                    ))
                elif msg['role'] == 'assistant':
                    contents.append(types.Content(
                        role='model',
                        parts=[types.Part(text=msg['content'])]
                    ))

            config = types.GenerateContentConfig(
                temperature=Config.TEMPERATURE,
                max_output_tokens=1024,
                system_instruction=system_instruction,
            )

            response = client.models.generate_content(
                model=Config.LLM_MODEL,
                contents=contents,
                config=config,
            )
            return response.text

    except Exception as e:
        logger.error(f"LLM call failed: {str(e)}")
        return f"I encountered an error processing your request: {str(e)}"


def parse_tool_call(response: str) -> Optional[dict]:
    """Parse a tool call from the LLM response."""
    # Try to find JSON in the response
    try:
        # First try direct JSON parse
        data = json.loads(response.strip())
        if 'tool' in data:
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the response
    json_match = re.search(r'\{[^{}]*"tool"[^{}]*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return None


def agent_node(state: AgentState) -> dict:
    """Main agent node that decides what to do."""
    client, provider = get_llm_client()

    # Build messages
    messages = [{"role": "system", "content": build_system_prompt()}]

    # Add conversation history
    for msg in state.get('messages', []):
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"role": "assistant", "content": msg.content})

    # Add tool results if any
    for result in state.get('tool_results', []):
        messages.append({"role": "user", "content": f"Tool result: {result}"})

    # Call LLM
    response = call_llm(messages, client, provider)

    # Check for tool call
    tool_call = parse_tool_call(response)

    if tool_call and state.get('iteration', 0) < Config.MAX_ITERATIONS:
        return {
            'messages': [AIMessage(content=response)],
            'tool_calls': [tool_call],
            'iteration': state.get('iteration', 0) + 1
        }
    else:
        # Clean up response if it contains tool call syntax but we're done iterating
        if tool_call:
            response = "I was unable to complete this request within the allowed iterations."

        return {
            'messages': [AIMessage(content=response)],
            'final_response': response,
            'iteration': state.get('iteration', 0) + 1
        }


def tool_node(state: AgentState) -> dict:
    """Execute tool calls."""
    tool_calls = state.get('tool_calls', [])
    results = []

    for call in tool_calls:
        tool_name = call.get('tool', '')
        args = call.get('args', {})

        logger.info(f"Executing tool: {tool_name} with args: {args}")

        result = execute_tool(tool_name, **args)
        results.append(result)

    return {
        'tool_results': results,
        'tool_calls': []
    }


def should_continue(state: AgentState) -> str:
    """Determine if we should continue to tools or end."""
    if state.get('final_response'):
        return 'end'
    if state.get('tool_calls'):
        return 'tools'
    return 'end'


def create_agent():
    """Create the LangGraph agent."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    # Set entry point
    workflow.set_entry_point("agent")

    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END
        }
    )

    # Tools always go back to agent
    workflow.add_edge("tools", "agent")

    return workflow.compile()


# Create singleton agent instance
_agent = None


def get_agent():
    """Get or create the agent instance."""
    global _agent
    if _agent is None:
        _agent = create_agent()
    return _agent


def invoke_agent(message: str) -> str:
    """
    Invoke the agent with a message and return the response.

    Args:
        message: User message to process

    Returns:
        Agent's response
    """
    agent = get_agent()

    initial_state = {
        'messages': [HumanMessage(content=message)],
        'tool_calls': [],
        'tool_results': [],
        'final_response': None,
        'iteration': 0
    }

    try:
        result = agent.invoke(initial_state)

        # Get final response
        if result.get('final_response'):
            return result['final_response']

        # Fall back to last message
        messages = result.get('messages', [])
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, AIMessage):
                return last_msg.content

        return "I was unable to generate a response."

    except Exception as e:
        logger.error(f"Agent invocation failed: {str(e)}", exc_info=True)
        return f"An error occurred: {str(e)}"
