"""
Unified OpenAI API interface.

Provides a single entry point for OpenAI completions using the Responses API.
Benefits: 40-80% better cache utilization, lower latency, simpler interface.

Key function: complete()
"""

from config import get_logger
from utils.openai_client import get_openai_client
from utils.app_config import get_configured_openai_model

logger = get_logger("ai")


def complete(
    messages=None,
    input_text=None,
    instructions=None,
    model=None,
    max_tokens=None,
    temperature=None,
    context=None,
):
    """
    Generate a completion using OpenAI's Responses API.

    Args:
        messages: List of message dicts with role/content (Chat Completions format)
                  Will be converted to Responses API format automatically.
        input_text: Direct text input (alternative to messages)
        instructions: System instructions (extracted from messages if not provided)
        model: Model to use (defaults to configured model)
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature
        context: Optional context string for logging (e.g., "BIRTHDAY_MESSAGE")

    Returns:
        str: The generated text response

    Raises:
        Exception: If API call fails
    """
    client = get_openai_client()
    model = model or get_configured_openai_model()
    context = context or "COMPLETION"

    # Build the API parameters
    params = {"model": model}

    # Handle input format
    if messages:
        # Extract system instruction if present
        system_content = None
        user_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                user_messages.append(msg)

        # Set instructions from system message or parameter
        if instructions:
            params["instructions"] = instructions
        elif system_content:
            params["instructions"] = system_content

        # Set input from user messages
        if len(user_messages) == 1:
            # Single user message - pass as string
            params["input"] = user_messages[0].get("content", "")
        elif user_messages:
            # Multiple messages - pass as list
            params["input"] = user_messages
        else:
            # No user messages, use system content as input
            params["input"] = system_content or ""

    elif input_text:
        params["input"] = input_text
        if instructions:
            params["instructions"] = instructions
    else:
        raise ValueError("Either 'messages' or 'input_text' must be provided")

    # Add optional parameters
    if max_tokens:
        params["max_output_tokens"] = max_tokens
    if temperature is not None:
        params["temperature"] = temperature

    logger.info(f"AI_{context}: Calling Responses API with model={model}")

    try:
        response = client.responses.create(**params)

        # Log usage if available
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            logger.info(
                f"AI_{context}_USAGE: "
                f"input={getattr(usage, 'input_tokens', 'N/A')}, "
                f"output={getattr(usage, 'output_tokens', 'N/A')}, "
                f"total={getattr(usage, 'total_tokens', 'N/A')}"
            )

        return response.output_text

    except Exception as e:
        logger.error(f"AI_{context}_ERROR: Responses API call failed: {e}")
        raise


def complete_with_usage(
    messages=None,
    input_text=None,
    instructions=None,
    model=None,
    max_tokens=None,
    temperature=None,
    context=None,
):
    """
    Generate a completion and return both text and usage info.

    Returns:
        tuple: (response_text, usage_dict) where usage_dict contains token counts
    """
    client = get_openai_client()
    model = model or get_configured_openai_model()
    context = context or "COMPLETION"

    # Build the API parameters
    params = {"model": model}

    # Handle input format
    if messages:
        system_content = None
        user_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                user_messages.append(msg)

        if instructions:
            params["instructions"] = instructions
        elif system_content:
            params["instructions"] = system_content

        if len(user_messages) == 1:
            params["input"] = user_messages[0].get("content", "")
        elif user_messages:
            params["input"] = user_messages
        else:
            params["input"] = system_content or ""

    elif input_text:
        params["input"] = input_text
        if instructions:
            params["instructions"] = instructions
    else:
        raise ValueError("Either 'messages' or 'input_text' must be provided")

    if max_tokens:
        params["max_output_tokens"] = max_tokens
    if temperature is not None:
        params["temperature"] = temperature

    logger.info(f"AI_{context}: Calling Responses API with model={model}")

    response = client.responses.create(**params)

    # Extract usage info
    usage_dict = {}
    if hasattr(response, "usage") and response.usage:
        usage = response.usage
        usage_dict = {
            "input_tokens": getattr(usage, "input_tokens", 0),
            "output_tokens": getattr(usage, "output_tokens", 0),
            "total_tokens": getattr(usage, "total_tokens", 0),
        }
        logger.info(
            f"AI_{context}_USAGE: "
            f"input={usage_dict['input_tokens']}, "
            f"output={usage_dict['output_tokens']}, "
            f"total={usage_dict['total_tokens']}"
        )

    return response.output_text, usage_dict
