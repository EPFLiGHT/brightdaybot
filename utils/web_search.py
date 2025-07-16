from openai import OpenAI
import json
import os
from datetime import datetime
from config import get_logger, CACHE_DIR, WEB_SEARCH_CACHE_ENABLED
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

        if personality == "mystic_dog":
            system_content = "You are Ludo the Mystic Birthday Dog, a cosmic canine whose powers reveal mystical insights about dates. Your task is to create a brief, mystical-sounding paragraph about the cosmic significance of a specific date, focusing on notable scientific figures born on this date and significant historical events. Use a mystical, slightly formal tone with cosmic metaphors. Include the year of those events."
            user_content = f"Based on these raw facts about {formatted_date}, create a paragraph that highlights 4-5 most significant scientific birthdays or events for this date in a mystical tone:\n\n{facts_text}"

        elif personality == "time_traveler":
            system_content = "You are Chrono, a time-traveling birthday messenger from the future. You have extensive knowledge of historical timelines. Create a brief, time-travel themed paragraph about significant historical events that occurred on this date. Focus on how these events shaped the future and include 1-2 humorous 'future facts' that connect to real historical events."
            user_content = f"Based on these historical facts about {formatted_date}, create a time-traveler's perspective of 3-4 significant events for this date in a lighthearted sci-fi tone:\n\n{facts_text}"

        elif personality == "superhero":
            system_content = "You are Captain Celebration, a birthday superhero. Create a brief, superhero-themed paragraph about notable achievements, discoveries, or heroic deeds that happened on this date. Use comic book style language, including bold exclamations and heroic metaphors."
            user_content = f"Based on these facts about {formatted_date}, create a superhero-style paragraph highlighting 3-4 'heroic' achievements or discoveries for this date:\n\n{facts_text}"

        elif personality == "pirate":
            system_content = "You are Captain BirthdayBeard, a pirate birthday messenger. Create a brief, pirate-themed paragraph about naval history, explorations, or 'treasure' discoveries that happened on this date. Use pirate speech patterns and nautical references."
            user_content = f"Based on these facts about {formatted_date}, create a pirate-style paragraph about 2-3 maritime events, explorations, or treasures discovered on this date:\n\n{facts_text}"

        elif personality == "poet":
            system_content = "You are The Verse-atile, a poetic birthday bard who creates lyrical birthday messages. Create a very brief poetic verse (4-6 lines) about historical events or notable people born on this date. Use elegant language, metaphors, and at least one clever rhyme. Focus on the beauty, significance, or wonder of these historical connections."
            user_content = f"Based on these facts about {formatted_date}, create a short poetic verse (4-6 lines) that references 2-3 notable events or people connected to this date:\n\n{facts_text}"

        elif personality == "tech_guru":
            system_content = "You are CodeCake, a tech-savvy birthday bot. Create a brief paragraph about technological innovations, scientific discoveries, or notable tech pioneers connected to this date. Use programming metaphors and tech terminology. Include at least one clever tech joke or pun based on the historical facts."
            user_content = f"Based on these facts about {formatted_date}, create a tech-themed paragraph highlighting 2-3 innovations, technological connections, or tech pioneers associated with this date:\n\n{facts_text}"

        elif personality == "chef":
            system_content = "You are Chef Confetti, a culinary birthday master. Create a brief, appetizing paragraph connecting this date to food history, culinary innovations, or 'recipe for success' stories that happened on this date. Use cooking metaphors and food-related terminology. Include at least one delicious food pun."
            user_content = f"Based on these facts about {formatted_date}, create a culinary-themed paragraph highlighting 2-3 food-related facts or using cooking metaphors to describe important events on this date:\n\n{facts_text}"

        elif personality == "standard":
            system_content = "You are BrightDay, a friendly, enthusiastic birthday bot. Create a brief, fun paragraph about 2-3 interesting historical events or notable people connected to this date. Use a friendly, conversational tone that's slightly over-the-top with enthusiasm. Focus on surprising or delightful connections that would make a birthday feel special."
            user_content = f"Based on these facts about {formatted_date}, create a brief, enthusiastic paragraph highlighting 2-3 fun or surprising facts about this date in history:\n\n{facts_text}"

        else:
            # Default to standard processing for other personalities
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
        # Parse the date
        day, month = map(int, date_str.split("/"))
        search_date = datetime(2025, month, day)  # Year doesn't matter for the search
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
        # Validate date format
        day, month = map(int, args.date.split("/"))
        if not (1 <= day <= 31 and 1 <= month <= 12):
            print(f"Error: Invalid date {args.date}. Day must be 1-31 and month 1-12.")
            return

        print(f"\n=== Searching for facts about {args.date} ===")
        date_obj = datetime(2025, month, day)  # Year doesn't matter
        formatted_date = date_obj.strftime("%B %d")
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

    except ValueError:
        print(f"Error: Date should be in DD/MM format (e.g., 25/12)")
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        print(traceback.format_exc())
    finally:
        # Restore original cache setting
        WEB_SEARCH_CACHE_ENABLED = original_cache_setting


if __name__ == "__main__":
    main()
