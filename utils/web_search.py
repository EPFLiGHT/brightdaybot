"""
Web search integration and historical facts retrieval for BrightDayBot.

Uses OpenAI's web search capabilities to find historical events and notable
people born on specific dates, with personality-specific formatting and caching.

Key functions: get_birthday_facts(), process_facts_for_personality().
"""

from openai import OpenAI
import json
import os
from datetime import datetime
from config import get_logger, CACHE_DIR, WEB_SEARCH_CACHE_ENABLED, DATE_FORMAT
import argparse
import sys

logger = get_logger("web_search")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def process_facts_for_personality(facts_text, formatted_date, personality):
    """
    Process the facts to create a concise paragraph suitable for different bot personalities

    Args:
        facts_text: Raw facts from the web search
        formatted_date: The date in "Month Day" format
        personality: The bot personality to format facts for ("mystic_dog", "time_traveler", etc.)

    Returns:
        Processed facts paragraph
    """
    try:
        system_content = ""
        user_content = ""

        # Get web search configuration from centralized personality config
        from personality_config import get_personality_config

        personality_config = get_personality_config(personality)

        system_content = personality_config.get("web_search_system", "")
        user_template = personality_config.get("web_search_user", "")

        if system_content and user_template:
            user_content = user_template.format(
                formatted_date=formatted_date, facts_text=facts_text
            )
        else:
            # Fallback to standard if no web search config found
            standard_config = get_personality_config("standard")
            system_content = standard_config.get("web_search_system", "")
            user_template = standard_config.get("web_search_user", "")

            if system_content and user_template:
                user_content = user_template.format(
                    formatted_date=formatted_date, facts_text=facts_text
                )
            else:
                # Ultimate fallback
                return f"On this day, {formatted_date}, several notable events occurred in history and remarkable individuals were born."

        # Use OpenAI to reformat the facts in the appropriate personality style
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            max_tokens=300,  # Reduced for more concise outputs
        )

        processed_facts = response.choices[0].message.content.strip()
        logger.info(
            f"WEB_SEARCH: Successfully processed facts for {formatted_date} using {personality} personality"
        )
        return processed_facts

    except Exception as e:
        logger.error(
            f"WEB_SEARCH_ERROR: Failed to process facts for {personality}: {e}"
        )
        # Return a simplified version of the original text if processing fails
        return f"On this day, {formatted_date}, several notable events occurred in history and remarkable individuals were born."


def get_birthday_facts(date_str, personality="mystic_dog"):
    """
    Get interesting facts about a specific date (like notable birthdays, especially in science)

    Args:
        date_str: Date in DD/MM format
        personality: The bot personality to format facts for (default: "mystic_dog")

    Returns:
        Dictionary with interesting facts and sources
    """
    # Include current year in cache filename so each year gets fresh results
    current_year = datetime.now().year
    cache_file = os.path.join(
        CACHE_DIR,
        f"facts_{date_str.replace('/', '_')}_{personality}_{current_year}.json",
    )

    # Periodically clean up old cache files (only once per day)
    if WEB_SEARCH_CACHE_ENABLED:
        cleanup_marker = os.path.join(
            CACHE_DIR, f"cleanup_{datetime.now().strftime('%Y_%m_%d')}"
        )
        if not os.path.exists(cleanup_marker):
            cleared = clear_old_cache_files()
            if cleared > 0:
                logger.info(f"CACHE: Auto-cleanup removed {cleared} old cache files")
            # Create marker file to prevent multiple cleanups per day
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
                open(cleanup_marker, "a").close()
            except Exception:
                pass  # Ignore cleanup marker creation errors

    # Check cache first if caching is enabled
    if WEB_SEARCH_CACHE_ENABLED and os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cached_data = json.load(f)
                logger.info(
                    f"WEB_SEARCH: Using cached results for {date_str} ({personality})"
                )
                return cached_data
        except Exception as e:
            logger.error(f"CACHE_ERROR: Failed to read cache: {e}")

    try:
        # Parse the date using datetime for proper validation
        date_obj = datetime.strptime(date_str, DATE_FORMAT)
        # Use any year for search formatting - year doesn't matter for historical events
        search_date = datetime(2025, date_obj.month, date_obj.day)
        formatted_date = search_date.strftime("%B %d")  # e.g. "April 15"

        # Customize search query based on personality
        if personality == "pirate":
            search_query = f"Naval history, maritime events, and exploration milestones that occurred on {formatted_date} throughout history"
        elif personality == "time_traveler":
            search_query = f"Significant historical events, technological milestones, and cultural shifts that occurred on {formatted_date} throughout history"
        elif personality == "superhero":
            search_query = f"Heroic achievements, scientific breakthroughs, and notable people born on {formatted_date} throughout history"
        elif personality == "poet":
            search_query = f"Literary figures, artistic achievements, and poetic events that occurred on {formatted_date} throughout history. Include poets born on this date."
        elif personality == "tech_guru":
            search_query = f"Technology inventions, computer science breakthroughs, and tech pioneers born on {formatted_date} throughout history"
        elif personality == "chef":
            search_query = f"Culinary history, food-related events, and famous chefs born on {formatted_date} throughout history. Also include any food discoveries or innovations."
        elif personality == "standard":
            search_query = f"Fun and interesting historical events and notable people born on {formatted_date} throughout history. Include surprising coincidences and remarkable achievements."
        else:
            # Default query for mystic_dog and others
            search_query = f"Notable people (especially scientists) born on {formatted_date} and significant historical events on this day"

        logger.info(
            f"WEB_SEARCH: Searching for facts about {formatted_date} for {personality}"
        )

        # Using the new responses.create method with web_search_preview tool
        response = client.responses.create(
            model="gpt-4.1",
            tools=[{"type": "web_search_preview"}],
            input=search_query,
        )

        logger.info(f"WEB_SEARCH: Received response for {formatted_date}")

        # Extract facts from the response
        facts_text = response.output_text

        # Since we're using the web search preview tool, sources might not be available in the same format
        sources = []

        if not facts_text:
            logger.warning(f"WEB_SEARCH: No facts found for {formatted_date}")
            return None

        # Process the facts text to make it suitable for the specified personality
        processed_facts = process_facts_for_personality(
            facts_text, formatted_date, personality
        )

        results = {
            "facts": processed_facts,
            "raw_facts": facts_text,  # Include the raw search results for testing
            "sources": sources,  # This will likely be empty with the web search preview tool
            "formatted_date": formatted_date,
            "personality": personality,  # Store which personality was used
        }

        # Save results to cache if caching is enabled
        if WEB_SEARCH_CACHE_ENABLED and results:
            try:
                # Ensure the cache directory exists
                os.makedirs(CACHE_DIR, exist_ok=True)

                with open(cache_file, "w") as f:
                    json.dump(results, f)
                    logger.info(
                        f"WEB_SEARCH: Cached results for {date_str} ({personality})"
                    )
            except Exception as e:
                logger.error(f"CACHE_ERROR: Failed to write to cache: {e}")

        return results

    except Exception as e:
        logger.error(f"WEB_SEARCH_ERROR: Failed to get birthday facts: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None


def clear_old_cache_files():
    """
    Clear web search cache files from previous years to prevent accumulation

    Returns:
        int: Number of old files cleared
    """
    try:
        if not os.path.exists(CACHE_DIR):
            return 0

        current_year = datetime.now().year
        cleared_count = 0

        for filename in os.listdir(CACHE_DIR):
            if filename.startswith("facts_") and filename.endswith(".json"):
                # Try to extract year from filename
                # Expected format: facts_DD_MM_personality_YYYY.json
                parts = filename.replace(".json", "").split("_")
                if len(parts) >= 4:
                    try:
                        file_year = int(parts[-1])  # Last part should be year
                        if file_year < current_year:
                            os.remove(os.path.join(CACHE_DIR, filename))
                            logger.info(
                                f"CACHE: Cleared old cache file from {file_year}: {filename}"
                            )
                            cleared_count += 1
                    except ValueError:
                        # Skip files that don't have year in expected format
                        continue

        if cleared_count > 0:
            logger.info(f"CACHE: Cleared {cleared_count} old cache files")

        return cleared_count

    except Exception as e:
        logger.error(f"CACHE_ERROR: Failed to clear old cache files: {e}")
        return 0


def clear_cache(date_str=None):
    """
    Clear web search cache

    Args:
        date_str: Optional specific date to clear (in DD/MM format)
                 If None, clears all cache

    Returns:
        int: Number of files cleared
    """
    try:
        if not os.path.exists(CACHE_DIR):
            logger.info("CACHE: No cache directory exists")
            return 0

        cleared_count = 0

        if date_str:
            # Clear specific date (all years and personalities)
            for filename in os.listdir(CACHE_DIR):
                if filename.startswith(f"facts_{date_str.replace('/', '_')}"):
                    os.remove(os.path.join(CACHE_DIR, filename))
                    logger.info(f"CACHE: Cleared cache for {date_str}")
                    cleared_count += 1
        else:
            # Clear all cache
            for filename in os.listdir(CACHE_DIR):
                if filename.startswith("facts_") and filename.endswith(".json"):
                    os.remove(os.path.join(CACHE_DIR, filename))
                    cleared_count += 1

            if cleared_count > 0:
                logger.info(f"CACHE: Cleared {cleared_count} cached files")

        return cleared_count

    except Exception as e:
        logger.error(f"CACHE_ERROR: Failed to clear cache: {e}")
        return 0


def main():
    """Main function for testing the web search functionality"""
    parser = argparse.ArgumentParser(description="Test the birthday facts web search")
    parser.add_argument(
        "--date",
        required=False,
        default="14/04",
        help="Birth date in DD/MM format (e.g., 25/12)",
    )
    parser.add_argument(
        "--raw", action="store_true", help="Show raw search results before processing"
    )
    parser.add_argument(
        "--sources", action="store_true", help="Show source URLs in the output"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear cached results before searching",
    )
    parser.add_argument(
        "--clear-all-cache",
        action="store_true",
        help="Clear all cached results (no search)",
    )
    parser.add_argument(
        "--clear-old-cache",
        action="store_true",
        help="Clear old cached results from previous years (no search)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable using/writing cache for this request",
    )
    parser.add_argument(
        "--personality",
        required=False,
        default="mystic_dog",
        help="Personality for formatting facts (e.g., mystic_dog, time_traveler, superhero, pirate)",
    )

    # Configure console logging for testing
    import logging

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - [%(levelname)s] %(message)s")
    )
    test_logger = logging.getLogger("birthday_bot.web_search_test")
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(console_handler)

    args = parser.parse_args()

    # Handle cache clearing
    if args.clear_all_cache:
        count = clear_cache()
        print(f"Cleared {count} cached files")
        return

    if args.clear_old_cache:
        count = clear_old_cache_files()
        print(f"Cleared {count} old cached files from previous years")
        return

    if args.clear_cache:
        clear_cache(args.date)
        print(f"Cleared cache for {args.date}")

    # Temporarily override cache setting if requested
    global WEB_SEARCH_CACHE_ENABLED
    original_cache_setting = WEB_SEARCH_CACHE_ENABLED

    if args.no_cache:
        WEB_SEARCH_CACHE_ENABLED = False
        print("Cache disabled for this request")

    try:
        # Validate date format using datetime parsing
        date_obj = datetime.strptime(args.date, DATE_FORMAT)

        print(f"\n=== Searching for facts about {args.date} ===")
        # Use any year for formatting - year doesn't matter for historical facts
        formatted_date_obj = datetime(2025, date_obj.month, date_obj.day)
        formatted_date = formatted_date_obj.strftime("%B %d")
        print(f"Searching for: {formatted_date}\n")

        if WEB_SEARCH_CACHE_ENABLED:
            print(f"Cache: ENABLED (set WEB_SEARCH_CACHE_ENABLED=false to disable)")
        else:
            print(f"Cache: DISABLED")

        # Call the function
        results = get_birthday_facts(args.date, args.personality)

        if not results:
            print("❌ No results found or an error occurred.")
            return

        print(f"\n=== Results for {formatted_date} ({args.personality}) ===\n")

        # Show raw results if requested
        if args.raw and "raw_facts" in results:
            print("RAW SEARCH RESULTS:")
            print("-" * 60)
            print(results["raw_facts"])
            print("-" * 60)
            print("\n")

        # Show processed facts
        print("FACTS:")
        print("-" * 60)
        print(results["facts"])
        print("-" * 60)

        # Show sources if requested
        if args.sources and results.get("sources"):
            print("\nSOURCES:")
            for i, source in enumerate(results["sources"], 1):
                print(f"{i}. {source.get('title', 'Unnamed Source')}")
                print(f"   {source.get('url', 'No URL')}")

    except ValueError as e:
        print(
            f"Error: Invalid date format '{args.date}'. Please use DD/MM format (e.g., 25/12)"
        )
        print(f"Details: {e}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        print(traceback.format_exc())
    finally:
        # Restore original cache setting
        WEB_SEARCH_CACHE_ENABLED = original_cache_setting


if __name__ == "__main__":
    main()
