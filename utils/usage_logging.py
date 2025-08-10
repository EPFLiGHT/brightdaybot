"""
Centralized usage logging for OpenAI API calls

This module provides consistent logging for all OpenAI API operations including
chat completions, image generation, and web search to monitor usage and costs.
"""


def log_chat_completion_usage(response, operation_name, logger):
    """
    Log token usage for chat completion API calls

    Args:
        response: OpenAI chat completion response object
        operation_name: String describing the operation (e.g., "SINGLE_BIRTHDAY", "WEB_SEARCH")
        logger: Logger instance to use for logging
    """
    try:
        usage = response.usage
        if usage:
            logger.info(
                f"{operation_name}_USAGE: Token usage - "
                f"prompt: {usage.prompt_tokens}, "
                f"completion: {usage.completion_tokens}, "
                f"total: {usage.total_tokens}"
            )
        else:
            logger.warning(
                f"{operation_name}_USAGE: No usage data available in response"
            )

    except Exception as e:
        logger.error(f"{operation_name}_USAGE: Failed to log token usage: {e}")


def log_image_generation_usage(
    response,
    operation_name,
    logger,
    image_count=1,
    quality=None,
    image_size=None,
    model=None,
):
    """
    Log usage for image generation API calls with enhanced parameter tracking

    Args:
        response: OpenAI image generation response object
        operation_name: String describing the operation (e.g., "IMAGE_GENERATION", "IMAGE_EDIT")
        logger: Logger instance to use for logging
        image_count: Number of images generated (default: 1)
        quality: Quality setting used ("low", "medium", "high", "auto")
        image_size: Size setting used (e.g., "1024x1024", "auto")
        model: Model used (e.g., "gpt-image-1")
    """
    try:
        # Image generation responses don't include token usage data (unlike chat completions)
        # But we can log cost-relevant parameters and estimate usage

        if hasattr(response, "data") and response.data:
            images_generated = len(response.data)

            # Basic generation info
            logger.info(
                f"{operation_name}_USAGE: Image generation completed - "
                f"images requested: {image_count}, "
                f"images generated: {images_generated}"
            )

            # Log generation timestamp if available
            if hasattr(response, "created") and response.created:
                from datetime import datetime

                timestamp = datetime.fromtimestamp(response.created).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                logger.info(f"{operation_name}_USAGE: Generated at: {timestamp}")

            # Log cost-affecting parameters
            cost_params = []
            if quality:
                cost_params.append(f"quality: {quality}")
            if image_size:
                cost_params.append(f"size: {image_size}")
            if model:
                cost_params.append(f"model: {model}")

            if cost_params:
                logger.info(
                    f"{operation_name}_USAGE: Parameters - {', '.join(cost_params)}"
                )

            # Log additional response info if available
            if hasattr(response.data[0], "model"):
                actual_model = response.data[0].model
                logger.info(f"{operation_name}_USAGE: Response model: {actual_model}")

        else:
            logger.warning(
                f"{operation_name}_USAGE: No image data available in response"
            )

    except Exception as e:
        logger.error(
            f"{operation_name}_USAGE: Failed to log image generation usage: {e}"
        )


def log_web_search_usage(response, operation_name, logger):
    """
    Log usage for web search API calls (responses.create)

    Args:
        response: OpenAI responses.create response object
        operation_name: String describing the operation (e.g., "WEB_SEARCH")
        logger: Logger instance to use for logging
    """
    try:
        # responses.create has a different usage format
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            # Check what attributes the ResponseUsage object has
            if hasattr(usage, "input_tokens") and hasattr(usage, "output_tokens"):
                # New format with input/output tokens
                total_tokens = (usage.input_tokens or 0) + (usage.output_tokens or 0)
                logger.info(
                    f"{operation_name}_USAGE: Token usage - "
                    f"input: {usage.input_tokens}, "
                    f"output: {usage.output_tokens}, "
                    f"total: {total_tokens}"
                )
            elif hasattr(usage, "prompt_tokens") and hasattr(
                usage, "completion_tokens"
            ):
                # Standard format
                logger.info(
                    f"{operation_name}_USAGE: Token usage - "
                    f"prompt: {usage.prompt_tokens}, "
                    f"completion: {usage.completion_tokens}, "
                    f"total: {usage.total_tokens}"
                )
            else:
                # Log whatever we can find
                logger.info(
                    f"{operation_name}_USAGE: Usage object available but format unknown: {usage}"
                )

        # Always log basic response info
        if hasattr(response, "output_text"):
            output_length = len(response.output_text) if response.output_text else 0
            logger.info(
                f"{operation_name}_USAGE: Web search completed - "
                f"output length: {output_length} characters"
            )
        else:
            logger.warning(
                f"{operation_name}_USAGE: No output_text in web search response"
            )

    except Exception as e:
        logger.error(f"{operation_name}_USAGE: Failed to log web search usage: {e}")


def log_generic_api_usage(response, operation_name, logger, additional_info=None):
    """
    Generic usage logging function that handles different response types

    Args:
        response: Any OpenAI API response object
        operation_name: String describing the operation
        logger: Logger instance to use for logging
        additional_info: Optional dictionary with extra info to log
    """
    try:
        logged_something = False

        # Try to log token usage (chat completions)
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            logger.info(
                f"{operation_name}_USAGE: Token usage - "
                f"prompt: {usage.prompt_tokens}, "
                f"completion: {usage.completion_tokens}, "
                f"total: {usage.total_tokens}"
            )
            logged_something = True

        # Try to log image data
        elif hasattr(response, "data") and response.data:
            images_count = len(response.data)
            logger.info(f"{operation_name}_USAGE: Generated {images_count} image(s)")
            logged_something = True

        # Try to log web search output
        elif hasattr(response, "output_text"):
            output_length = len(response.output_text) if response.output_text else 0
            logger.info(
                f"{operation_name}_USAGE: Output length: {output_length} characters"
            )
            logged_something = True

        # Log additional info if provided
        if additional_info:
            for key, value in additional_info.items():
                logger.info(f"{operation_name}_USAGE: {key}: {value}")
                logged_something = True

        if not logged_something:
            logger.warning(
                f"{operation_name}_USAGE: No recognizable usage data in response"
            )

    except Exception as e:
        logger.error(f"{operation_name}_USAGE: Failed to log API usage: {e}")
