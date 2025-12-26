"""
NLP Date Parser for BrightDayBot

Uses LLM to extract dates from natural language input when regex parsing fails.
Handles inputs like:
- "my birthday is July 14th, 1990"
- "I was born on the 25th of December"
- "born March 5"

Falls back gracefully on LLM errors.
"""

import json
from typing import Optional, Dict, Any
from datetime import datetime

from config import get_logger, MIN_BIRTH_YEAR

logger = get_logger("ai")


def parse_date_with_nlp(text: str) -> Dict[str, Any]:
    """
    Parse a date from natural language text using LLM.

    Args:
        text: User input text containing a date

    Returns:
        Dict with:
        - status: 'success', 'ambiguous', or 'error'
        - day: int or None
        - month: int or None
        - year: int or None (optional birth year)
        - error: str or None
    """
    result = {
        "status": "error",
        "day": None,
        "month": None,
        "year": None,
        "error": None,
    }

    try:
        # Early return for empty input
        if not text or not text.strip():
            result["error"] = "Empty text provided"
            return result

        from config import NLP_DATE_PARSING_ENABLED

        if not NLP_DATE_PARSING_ENABLED:
            result["error"] = "NLP date parsing is disabled"
            return result

        # Try regex first (fast path)
        regex_result = _try_regex_parse(text)
        if regex_result["status"] == "success":
            return regex_result

        # Fall back to LLM
        llm_result = _parse_with_llm(text)
        return llm_result

    except ImportError:
        result["error"] = "NLP date parsing config not available"
        return result
    except Exception as e:
        logger.error(f"NLP_DATE_PARSER: Error parsing date: {e}")
        result["error"] = str(e)
        return result


def _try_regex_parse(text: str) -> Dict[str, Any]:
    """
    Try to parse date using existing regex patterns.

    Returns:
        Dict with parsing result
    """
    from utils.date import extract_date

    result = extract_date(text)

    if result["status"] == "success":
        day, month = result["date"].split("/")[:2]

        # Check for year
        year = None
        parts = result["date"].split("/")
        if len(parts) == 3:
            year = int(parts[2])

        return {
            "status": "success",
            "day": int(day),
            "month": int(month),
            "year": year,
            "error": None,
        }

    return {"status": "error", "day": None, "month": None, "year": None, "error": None}


def _parse_with_llm(text: str) -> Dict[str, Any]:
    """
    Parse date using LLM when regex fails.

    Args:
        text: User input text

    Returns:
        Dict with parsing result
    """
    try:
        from integrations.openai import complete
        from config import TOKEN_LIMITS, TEMPERATURE_SETTINGS

        prompt = f"""Extract the birthday date from this text. Return ONLY a JSON object with day, month, and year (if provided).

Text: "{text}"

Rules:
- day: integer 1-31
- month: integer 1-12
- year: integer (4 digits) or null if not provided
- If the date is ambiguous (like "04/05" where it's unclear if it's April 5 or May 4), set "ambiguous": true
- If no date is found, return {{"error": "no date found"}}

Examples:
- "my birthday is July 14th" → {{"day": 14, "month": 7, "year": null}}
- "born on December 25, 1990" → {{"day": 25, "month": 12, "year": 1990}}
- "I was born 05/04" → {{"day": null, "month": null, "year": null, "ambiguous": true, "options": ["April 5", "May 4"]}}

Return ONLY the JSON object, no explanation:"""

        response = complete(
            input_text=prompt,
            max_tokens=TOKEN_LIMITS.get("date_parsing", 100),
            temperature=TEMPERATURE_SETTINGS.get("factual", 0.3),
            context="DATE_PARSING",
        )

        if not response:
            return {
                "status": "error",
                "day": None,
                "month": None,
                "year": None,
                "error": "No LLM response",
            }

        # Parse the JSON response
        return _parse_llm_response(response)

    except Exception as e:
        logger.error(f"NLP_DATE_PARSER: LLM parsing failed: {e}")
        return {
            "status": "error",
            "day": None,
            "month": None,
            "year": None,
            "error": str(e),
        }


def _parse_llm_response(response: str) -> Dict[str, Any]:
    """
    Parse the LLM JSON response.

    Args:
        response: LLM response text

    Returns:
        Dict with parsing result
    """
    try:
        # Clean the response - extract JSON if wrapped in markdown
        response = response.strip()
        if response.startswith("```"):
            # Remove markdown code block
            lines = response.split("\n")
            response = "\n".join(line for line in lines if not line.startswith("```"))

        # Parse JSON
        data = json.loads(response)

        # Check for error
        if "error" in data:
            return {
                "status": "error",
                "day": None,
                "month": None,
                "year": None,
                "error": data["error"],
            }

        # Check for ambiguity
        if data.get("ambiguous"):
            return {
                "status": "ambiguous",
                "day": None,
                "month": None,
                "year": None,
                "options": data.get("options", []),
                "error": None,
            }

        # Extract date components
        day = data.get("day")
        month = data.get("month")
        year = data.get("year")

        # Validate
        if not day or not month:
            return {
                "status": "error",
                "day": None,
                "month": None,
                "year": None,
                "error": "Incomplete date",
            }

        # Validate ranges
        if not (1 <= day <= 31) or not (1 <= month <= 12):
            return {
                "status": "error",
                "day": None,
                "month": None,
                "year": None,
                "error": "Invalid date values",
            }

        if year and not (MIN_BIRTH_YEAR <= year <= datetime.now().year):
            year = None  # Ignore invalid years

        return {
            "status": "success",
            "day": int(day),
            "month": int(month),
            "year": int(year) if year else None,
            "error": None,
        }

    except json.JSONDecodeError as e:
        logger.error(f"NLP_DATE_PARSER: JSON parse error: {e}")
        return {
            "status": "error",
            "day": None,
            "month": None,
            "year": None,
            "error": "Failed to parse LLM response",
        }


def format_parsed_date(result: Dict[str, Any]) -> str:
    """
    Format parsed date to DD/MM or DD/MM/YYYY string.

    Args:
        result: Parsing result dict

    Returns:
        Formatted date string or empty string if invalid
    """
    if result["status"] != "success":
        return ""

    day = result["day"]
    month = result["month"]
    year = result.get("year")

    if year:
        return f"{day:02d}/{month:02d}/{year}"
    else:
        return f"{day:02d}/{month:02d}"
