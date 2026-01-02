#!/usr/bin/env python3
"""
Migration script to convert birthdays.txt (CSV) to birthdays.json format.

This script:
1. Reads existing birthdays.txt in CSV format
2. Converts to JSON format with preferences
3. Creates backup of original file
4. Writes birthdays.json

Run with: python scripts/migrate_birthdays.py
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import BACKUP_DIR, STORAGE_DIR


def migrate_csv_to_json():
    """
    Migrate birthdays from CSV format to JSON format with preferences.

    Returns:
        tuple: (success: bool, message: str, count: int)
    """
    csv_file = os.path.join(STORAGE_DIR, "birthdays.txt")
    json_file = os.path.join(STORAGE_DIR, "birthdays.json")

    # Check if CSV file exists
    if not os.path.exists(csv_file):
        return False, f"CSV file not found: {csv_file}", 0

    # Check if JSON already exists (don't overwrite)
    if os.path.exists(json_file):
        return False, f"JSON file already exists: {json_file}. Delete it first to re-migrate.", 0

    # Read CSV and convert
    birthdays = {}
    now = datetime.now(timezone.utc).isoformat()

    try:
        with open(csv_file, "r") as f:
            for line_number, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                parts = line.split(",")
                if len(parts) < 2:
                    print(f"  Warning: Skipping invalid line {line_number}: {line}")
                    continue

                user_id = parts[0].strip()
                date = parts[1].strip()

                # Parse optional year
                year = None
                if len(parts) > 2 and parts[2].strip():
                    try:
                        year = int(parts[2].strip())
                    except ValueError:
                        print(f"  Warning: Invalid year at line {line_number}: {parts[2]}")

                # Create new format with preferences
                birthdays[user_id] = {
                    "date": date,
                    "year": year,
                    "preferences": {
                        "active": True,
                        "image_enabled": True,
                        "show_age": year is not None,  # Default based on whether year provided
                    },
                    "created_at": now,
                    "updated_at": now,
                }

        if not birthdays:
            return False, "No valid birthday entries found in CSV", 0

        # Create backup of original CSV
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(BACKUP_DIR, f"birthdays_pre_migration_{timestamp}.txt")
        shutil.copy2(csv_file, backup_file)
        print(f"  Created backup: {backup_file}")

        # Write JSON file
        with open(json_file, "w") as f:
            json.dump(birthdays, f, indent=2)

        return True, f"Successfully migrated {len(birthdays)} birthdays to JSON", len(birthdays)

    except Exception as e:
        return False, f"Migration failed: {e}", 0


def verify_migration():
    """
    Verify the migration was successful by comparing counts.

    Returns:
        tuple: (success: bool, message: str)
    """
    csv_file = os.path.join(STORAGE_DIR, "birthdays.txt")
    json_file = os.path.join(STORAGE_DIR, "birthdays.json")

    # Count CSV entries
    csv_count = 0
    try:
        with open(csv_file, "r") as f:
            for line in f:
                if line.strip() and len(line.strip().split(",")) >= 2:
                    csv_count += 1
    except Exception as e:
        return False, f"Failed to read CSV: {e}"

    # Count JSON entries
    try:
        with open(json_file, "r") as f:
            data = json.load(f)
            json_count = len(data)
    except Exception as e:
        return False, f"Failed to read JSON: {e}"

    if csv_count == json_count:
        return True, f"Verification passed: {json_count} entries in both files"
    else:
        return False, f"Count mismatch: CSV has {csv_count}, JSON has {json_count}"


def main():
    print("=" * 60)
    print("BrightDayBot Birthday Storage Migration")
    print("CSV (birthdays.txt) -> JSON (birthdays.json)")
    print("=" * 60)
    print()

    # Run migration
    print("Step 1: Migrating data...")
    success, message, count = migrate_csv_to_json()
    print(f"  {message}")

    if not success:
        print("\nMigration failed. No changes made.")
        sys.exit(1)

    # Verify migration
    print("\nStep 2: Verifying migration...")
    success, message = verify_migration()
    print(f"  {message}")

    if not success:
        print("\nVerification failed! Check the files manually.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print()
    print("Next steps:")
    print("1. The original birthdays.txt has been backed up")
    print("2. New birthdays.json is now ready to use")
    print("3. After confirming everything works, you can delete birthdays.txt")
    print("=" * 60)


if __name__ == "__main__":
    main()
