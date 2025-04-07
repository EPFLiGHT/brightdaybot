from openai import OpenAI
import json
import os
from datetime import datetime
from config import get_logger, CACHE_DIR
import argparse
import sys

logger = get_logger("web_search")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_birthday_facts(date_str):
    """
    Get interesting facts about a specific date (like notable birthdays, especially in science)

    Args:
        date_str: Date in DD/MM format

    Returns:
        Dictionary with interesting facts and sources
    """
    cache_file = os.path.join(CACHE_DIR, f"facts_{date_str.replace('/', '_')}.json")

    # Check cache first
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cached_data = json.load(f)
                logger.info(f"WEB_SEARCH: Using cached results for {date_str}")
                return cached_data
        except Exception as e:
            logger.error(f"CACHE_ERROR: Failed to read cache: {e}")

    try:
        # Parse the date
        day, month = map(int, date_str.split("/"))
        search_date = datetime(2025, month, day)  # Year doesn't matter for the search
        formatted_date = search_date.strftime("%B %d")  # e.g. "April 15"

        search_query = f"Notable people (especially scientists) born on {formatted_date} and significant historical events on this day"

        logger.info(f"WEB_SEARCH: Searching for facts about {formatted_date}")

        # Using gpt-4o-search-preview for web search capability
        response = client.chat.completions.create(
            model="gpt-4o-search-preview",
            messages=[{"role": "user", "content": search_query}],
            max_tokens=500,
        )

        logger.info(f"WEB_SEARCH: Received response for {formatted_date}")

        # Extract facts from the response - this is a ChatCompletion object
        facts_text = response.choices[0].message.content

        # Since we're using search preview, sources are not directly available in the response
        # We'll work with the content directly
        sources = []

        if not facts_text:
            logger.warning(f"WEB_SEARCH: No facts found for {formatted_date}")
            return None

        # Process the facts text to make it suitable for Ludo's message
        processed_facts = process_facts_for_ludo(facts_text, formatted_date)

        results = {
            "facts": processed_facts,
            "raw_facts": facts_text,  # Include the raw search results for testing
            "sources": sources,  # This will be empty with the search preview model
            "formatted_date": formatted_date,
        }

        # Save results to cache before returning
        if results:
            try:
                with open(cache_file, "w") as f:
                    json.dump(results, f)
            except Exception as e:
                logger.error(f"CACHE_ERROR: Failed to write to cache: {e}")

        return results

    except Exception as e:
        logger.error(f"WEB_SEARCH_ERROR: Failed to get birthday facts: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None


def process_facts_for_ludo(facts_text, formatted_date):
    """
    Process the facts to create a concise, focused paragraph suitable for Ludo's mystical style

    Args:
        facts_text: Raw facts from the web search
        formatted_date: The date in "Month Day" format

    Returns:
        Processed facts paragraph
    """
    try:
        # Use OpenAI to reformat the facts in Ludo's style
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are Ludo the Mystic Birthday Dog, a cosmic canine whose powers reveal mystical insights about dates. Your task is to create a brief, mystical-sounding paragraph about the cosmic significance of a specific date, focusing on notable scientific figures born on this date and significant historical events. Use a mystical, slightly formal tone with cosmic metaphors. Include the year of those events.",
                },
                {
                    "role": "user",
                    "content": f"Based on these raw facts about {formatted_date}, create a paragraph that highlights 4-5 most significant scientific birthdays or events for this date in a mystical tone:\n\n{facts_text}",
                },
            ],
            max_tokens=500,
        )

        processed_facts = response.choices[0].message.content.strip()
        logger.info(f"WEB_SEARCH: Successfully processed facts for {formatted_date}")
        return processed_facts

    except Exception as e:
        logger.error(f"WEB_SEARCH_ERROR: Failed to process facts: {e}")
        # Return a simplified version of the original text if processing fails
        return f"On this day, {formatted_date}, the cosmos aligned to welcome several notable souls to our realm."


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

        # Call the function
        results = get_birthday_facts(args.date)

        if not results:
            print("❌ No results found or an error occurred.")
            return

        print(f"\n=== Results for {formatted_date} ===\n")

        # Show raw results if requested
        if args.raw and "raw_facts" in results:
            print("RAW SEARCH RESULTS:")
            print("-" * 60)
            print(results["raw_facts"])
            print("-" * 60)
            print("\n")

        # Show processed facts
        print("MYSTICAL FACTS FOR LUDO:")
        print("-" * 60)
        print(results["facts"])
        print("-" * 60)

        # Show sources if requested
        if args.sources and results["sources"]:
            print("\nSOURCES:")
            for i, source in enumerate(results["sources"], 1):
                print(f"{i}. {source.get('title', 'Unnamed Source')}")
                print(f"   {source.get('url', 'No URL')}")

    except ValueError:
        print(f"Error: Date should be in DD/MM format (e.g., 25/12)")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
