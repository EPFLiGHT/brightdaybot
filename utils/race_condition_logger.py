"""
Race condition monitoring and logging utilities for birthday celebrations.

Provides detailed logging of race conditions, validation results, and data
consistency issues to help administrators monitor system reliability.

Key functions: log_race_condition_detection(), create_race_condition_summary().
"""

from datetime import datetime, timezone
from utils.logging_config import get_logger

logger = get_logger("birthday")


def log_race_condition_detection(
    validation_result, original_count, processing_duration=None, context="UNKNOWN"
):
    """
    Log detailed race condition detection results for monitoring and debugging.

    Args:
        validation_result: Result from validate_birthday_people_for_posting()
        original_count: Number of people at start of processing
        processing_duration: How long AI processing took (seconds)
        context: Context string (TIMEZONE, SIMPLE_DAILY, MISSED_BIRTHDAYS)
    """
    summary = validation_result["validation_summary"]
    invalid_people = validation_result["invalid_people"]

    if summary["invalid"] == 0:
        logger.info(
            f"RACE_CONDITION_CHECK: {context} - No race conditions detected ({summary['valid']}/{summary['total']} people valid)"
        )
        return

    # Log race condition detection
    invalid_fraction = (
        summary["invalid"] / summary["total"] if summary["total"] > 0 else 0
    )
    logger.warning(
        f"RACE_CONDITION_DETECTED: {context} - {summary['invalid']}/{summary['total']} people became invalid during processing ({invalid_fraction:.1%})"
    )

    # Log timing information if available
    if processing_duration:
        logger.warning(
            f"RACE_CONDITION_TIMING: Processing took {processing_duration:.1f}s - longer processing increases race condition risk"
        )

    # Log detailed breakdown of reasons
    reasons = summary["reasons"]
    for reason, count in reasons.items():
        logger.warning(f"RACE_CONDITION_REASON: {reason} affected {count} people")

        # Log specific people for each reason (helps with debugging)
        affected_people = [
            p for p in invalid_people if p.get("invalid_reason") == reason
        ]
        names = [p.get("username", p["user_id"]) for p in affected_people]
        logger.info(f"RACE_CONDITION_DETAILS: {reason} - {', '.join(names)}")

    # Log severity assessment
    if invalid_fraction >= 0.5:
        logger.error(
            f"RACE_CONDITION_CRITICAL: {invalid_fraction:.1%} of people invalid - major data inconsistency detected"
        )
    elif invalid_fraction >= 0.3:
        logger.warning(
            f"RACE_CONDITION_MODERATE: {invalid_fraction:.1%} of people invalid - significant changes during processing"
        )
    else:
        logger.info(
            f"RACE_CONDITION_MINOR: {invalid_fraction:.1%} of people invalid - minor changes handled gracefully"
        )


def log_validation_action_taken(
    action_type, valid_count, total_count, context="UNKNOWN"
):
    """
    Log what action was taken in response to validation results.

    Args:
        action_type: "regenerated", "filtered", "skipped", or "proceeded"
        valid_count: Number of valid people
        total_count: Original number of people
        context: Context string for logging
    """
    if action_type == "regenerated":
        logger.info(
            f"RACE_CONDITION_ACTION: {context} - Regenerated message for {valid_count} people (filtered out {total_count - valid_count})"
        )
    elif action_type == "filtered":
        logger.info(
            f"RACE_CONDITION_ACTION: {context} - Used original message but filtered images for {valid_count} people"
        )
    elif action_type == "skipped":
        logger.warning(
            f"RACE_CONDITION_ACTION: {context} - Skipped celebration entirely (all {total_count} people became invalid)"
        )
    elif action_type == "proceeded":
        logger.info(
            f"RACE_CONDITION_ACTION: {context} - Proceeded with original message ({valid_count} people still valid)"
        )


def create_race_condition_summary(validation_results_list):
    """
    Create a summary of race conditions detected across multiple celebrations.

    Args:
        validation_results_list: List of validation results from different celebrations

    Returns:
        dict: Summary statistics about race conditions
    """
    total_celebrations = len(validation_results_list)
    celebrations_with_issues = 0
    total_people_processed = 0
    total_people_filtered = 0
    reason_counts = {}

    for result in validation_results_list:
        summary = result["validation_summary"]
        total_people_processed += summary["total"]
        total_people_filtered += summary["invalid"]

        if summary["invalid"] > 0:
            celebrations_with_issues += 1

        for reason, count in summary["reasons"].items():
            reason_counts[reason] = reason_counts.get(reason, 0) + count

    race_condition_rate = (
        celebrations_with_issues / total_celebrations if total_celebrations > 0 else 0
    )
    overall_invalid_rate = (
        total_people_filtered / total_people_processed
        if total_people_processed > 0
        else 0
    )

    summary_dict = {
        "total_celebrations": total_celebrations,
        "celebrations_with_race_conditions": celebrations_with_issues,
        "race_condition_rate": race_condition_rate,
        "total_people_processed": total_people_processed,
        "total_people_filtered": total_people_filtered,
        "overall_invalid_rate": overall_invalid_rate,
        "top_reasons": reason_counts,
    }

    logger.info(
        f"RACE_CONDITION_SUMMARY: {celebrations_with_issues}/{total_celebrations} celebrations had race conditions "
        f"({race_condition_rate:.1%} rate). {total_people_filtered}/{total_people_processed} people filtered "
        f"({overall_invalid_rate:.1%} overall invalid rate)"
    )

    return summary_dict


def log_birthday_data_change_impact(user_id, username, change_type, timing_context):
    """
    Log when birthday data changes are detected and their potential impact.

    Args:
        user_id: User whose birthday data changed
        username: Username for logging
        change_type: "added_today", "removed_today", "changed_away", "profile_updated"
        timing_context: When this was detected ("during_processing", "pre_posting", etc.)
    """
    impact_messages = {
        "added_today": f"User {username} added birthday for today {timing_context}",
        "removed_today": f"User {username} removed birthday {timing_context}",
        "changed_away": f"User {username} changed birthday away from today {timing_context}",
        "profile_updated": f"User {username} updated profile {timing_context}",
    }

    message = impact_messages.get(
        change_type, f"User {username} made unknown change {timing_context}"
    )

    if timing_context == "during_processing":
        logger.warning(f"BIRTHDAY_DATA_CHANGE: {message} - potential race condition")
    else:
        logger.info(f"BIRTHDAY_DATA_CHANGE: {message}")


def should_alert_on_race_conditions(validation_result, alert_threshold=0.2):
    """
    Determine if race condition detection should trigger an alert.

    Args:
        validation_result: Result from validate_birthday_people_for_posting()
        alert_threshold: Alert if more than this fraction of people are invalid

    Returns:
        bool: True if should alert administrators
    """
    summary = validation_result["validation_summary"]

    if summary["total"] == 0:
        return False

    invalid_fraction = summary["invalid"] / summary["total"]
    should_alert = invalid_fraction > alert_threshold

    if should_alert:
        logger.error(
            f"RACE_CONDITION_ALERT: High race condition rate detected - {invalid_fraction:.1%} > {alert_threshold:.1%} threshold. "
            f"Consider investigating birthday data change patterns."
        )

    return should_alert
