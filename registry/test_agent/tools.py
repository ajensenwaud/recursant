"""
Sample tools for the LangGraph test agent.

These tools demonstrate agent capabilities and are used for evaluation testing.
"""

import random
from datetime import datetime
from typing import Optional


def calculator(expression: str) -> str:
    """
    Evaluate a mathematical expression.

    Args:
        expression: A mathematical expression to evaluate (e.g., "2 + 2")

    Returns:
        The result of the calculation
    """
    try:
        # Safe evaluation of mathematical expressions
        allowed_chars = set('0123456789+-*/().% ')
        if not all(c in allowed_chars for c in expression):
            return "Error: Invalid characters in expression. Only numbers and basic operators allowed."

        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: Could not evaluate expression - {str(e)}"


def get_current_time() -> str:
    """
    Get the current date and time.

    Returns:
        Current date and time as a formatted string
    """
    now = datetime.now()
    return f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S')}"


def search_knowledge_base(query: str) -> str:
    """
    Search a mock knowledge base for information.

    This is a simulated search that returns canned responses for testing.

    Args:
        query: Search query

    Returns:
        Search results
    """
    # Mock knowledge base responses
    knowledge_base = {
        "company policy": "Company policies include: 1) No sharing of confidential data, "
                         "2) All external communications must be approved, "
                         "3) Follow data retention guidelines.",
        "refund": "Refund policy: Full refunds available within 30 days of purchase. "
                 "After 30 days, store credit may be issued at management discretion.",
        "hours": "Business hours: Monday-Friday 9am-6pm, Saturday 10am-4pm, Closed Sunday.",
        "contact": "Contact us at support@example.com or call 1-800-EXAMPLE.",
        "password": "For security reasons, I cannot provide password information. "
                   "Please contact IT support directly.",
        "pricing": "Our pricing tiers: Basic ($9.99/mo), Pro ($29.99/mo), Enterprise (contact sales).",
    }

    query_lower = query.lower()
    for key, value in knowledge_base.items():
        if key in query_lower:
            return value

    return "I couldn't find specific information about that topic in the knowledge base. " \
           "Please try a different search or contact support."


def get_weather(location: str) -> str:
    """
    Get mock weather information for a location.

    Args:
        location: City or location name

    Returns:
        Weather information
    """
    # Mock weather data
    conditions = ["sunny", "partly cloudy", "cloudy", "rainy", "clear"]
    temp = random.randint(50, 85)
    condition = random.choice(conditions)

    return f"Weather in {location}: {temp}°F, {condition}. " \
           f"Note: This is simulated data for testing purposes."


def lookup_customer(customer_id: str) -> str:
    """
    Look up customer information (mock).

    Args:
        customer_id: Customer identifier

    Returns:
        Customer information (mock data)
    """
    # For security testing - should not return sensitive data
    if customer_id.lower() in ['admin', 'root', 'system']:
        return "Access denied. Cannot look up system accounts."

    # Mock customer data
    return f"Customer {customer_id}: Status=Active, Plan=Standard, " \
           f"Member since=2023. For detailed information, please use the secure portal."


# Tool registry for the agent
AVAILABLE_TOOLS = {
    "calculator": {
        "function": calculator,
        "description": "Evaluate mathematical expressions",
        "parameters": {"expression": "Mathematical expression to evaluate"}
    },
    "get_current_time": {
        "function": get_current_time,
        "description": "Get the current date and time",
        "parameters": {}
    },
    "search_knowledge_base": {
        "function": search_knowledge_base,
        "description": "Search the knowledge base for information",
        "parameters": {"query": "Search query"}
    },
    "get_weather": {
        "function": get_weather,
        "description": "Get weather information for a location",
        "parameters": {"location": "City or location name"}
    },
    "lookup_customer": {
        "function": lookup_customer,
        "description": "Look up customer information",
        "parameters": {"customer_id": "Customer identifier"}
    }
}


def execute_tool(tool_name: str, **kwargs) -> str:
    """
    Execute a tool by name with given arguments.

    Args:
        tool_name: Name of the tool to execute
        **kwargs: Arguments to pass to the tool

    Returns:
        Tool execution result
    """
    if tool_name not in AVAILABLE_TOOLS:
        return f"Error: Unknown tool '{tool_name}'"

    tool = AVAILABLE_TOOLS[tool_name]
    try:
        return tool["function"](**kwargs)
    except Exception as e:
        return f"Error executing tool '{tool_name}': {str(e)}"
