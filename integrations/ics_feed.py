"""
External ICS Calendar Feed Subscription Client

Allows admins to subscribe to external ICS/webcal calendar feeds.
Events are fetched, parsed, cached, and surfaced as SpecialDays.

Security: SSRF prevention via URL validation, DNS pinning, and redirect validation.
"""

import ipaddress
import json
import os
import re
import socket
import threading
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from icalendar import Calendar

from config import (
    ICS_CACHE_DIR,
    ICS_CACHE_TTL_DAYS,
    ICS_MAX_CONSECUTIVE_FAILURES,
    ICS_MAX_EVENTS_PER_FEED,
    ICS_MAX_FILE_SIZE_BYTES,
    ICS_MAX_SUBSCRIPTIONS,
    ICS_SUBSCRIPTIONS_ENABLED,
    ICS_SUBSCRIPTIONS_FILE,
    TIMEOUTS,
    get_logger,
)
from utils.sanitization import sanitize_for_prompt, sanitize_slack_text

logger = get_logger("special_days")

_client: Optional["ICSFeedClient"] = None
_client_lock = threading.Lock()
_dns_pin_lock = threading.Lock()

_MAX_REDIRECTS = 3
_MAX_EVENT_URL_LENGTH = 512
_DANGEROUS_RRULE_FREQS = {"SECONDLY", "MINUTELY", "HOURLY"}
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]{0,30}$")


def get_ics_feed_client() -> "ICSFeedClient":
    """Get or create the singleton ICS feed client (thread-safe)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = ICSFeedClient()
    return _client


# ---- SSRF Prevention ----


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP is private, reserved, loopback, link-local, or multicast."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_dns_and_validate(hostname: str) -> str:
    """Resolve hostname and validate all IPs are public.

    Returns the first valid IP address string.
    Raises ValueError if resolution fails or all IPs are blocked.
    """
    try:
        results = socket.getaddrinfo(hostname, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not results:
            raise ValueError(f"Could not resolve hostname: {hostname}")
    except socket.gaierror:
        raise ValueError(f"DNS resolution failed for {hostname}")

    first_valid_ip = None
    for family, _, _, _, sockaddr in results:
        ip = ipaddress.ip_address(sockaddr[0])
        if _is_blocked_ip(ip):
            raise ValueError(f"Blocked: {hostname} resolves to private/reserved IP")
        if first_valid_ip is None:
            first_valid_ip = sockaddr[0]

    return first_valid_ip


def validate_ics_url(url: str) -> tuple:
    """Validate URL is safe for ICS fetching.

    Returns (is_valid, url_or_error) for simple validation,
    or (is_valid, url, resolved_ip) when DNS resolution succeeds.
    Callers that only need a boolean check can ignore the third element.
    """
    if not url:
        return False, "URL is empty", None

    # Convert webcal:// to https://
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]

    # Must be HTTPS
    if not url.startswith("https://"):
        return False, "Only HTTPS URLs are allowed", None

    # No auth in URL
    if "@" in url.split("/")[2]:
        return False, "URLs with credentials are not allowed", None

    # URL length
    if len(url) > 2048:
        return False, "URL too long (max 2048 chars)", None

    # Extract hostname
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False, "Could not parse hostname", None
    except Exception:
        return False, "Invalid URL format", None

    # No raw IP addresses
    try:
        ipaddress.ip_address(hostname)
        return False, "Raw IP addresses are not allowed — use a hostname", None
    except ValueError:
        pass  # Good — it's a hostname, not an IP

    # DNS resolution + IP validation (single resolution, reused for pinning)
    try:
        resolved_ip = _resolve_dns_and_validate(hostname)
    except ValueError as e:
        return False, str(e), None

    return True, url, resolved_ip  # Return sanitized URL + validated IP


def _fetch_with_pinned_dns(url: str, hostname: str, pinned_ip: str, **kwargs) -> requests.Response:
    """Make HTTP request with DNS pinned to a pre-validated IP (prevents DNS rebinding).

    Uses urllib3's create_connection override to force the connection to the
    validated IP while keeping the original hostname for SSL/SNI verification.
    """
    import urllib3.util.connection as urllib3_cn

    original_create_connection = urllib3_cn.create_connection

    def pinned_create_connection(address, *args, **kw):
        host, port = address
        if host == hostname:
            return original_create_connection((pinned_ip, port), *args, **kw)
        return original_create_connection(address, *args, **kw)

    with _dns_pin_lock:
        urllib3_cn.create_connection = pinned_create_connection
        try:
            return requests.get(url, **kwargs)
        finally:
            urllib3_cn.create_connection = original_create_connection


# ---- Data Model ----


@dataclass
class ICSSubscription:
    """An external ICS calendar feed subscription."""

    id: str
    url: str
    label: str
    enabled: bool = True
    category: str = "Company"
    emoji: str = "📅"
    added_by: str = ""
    added_at: str = ""
    last_fetched: str = ""
    last_error: str = ""
    event_count: int = 0
    consecutive_failures: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "ICSSubscription":
        filtered = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}

        # Validate ID: must match safe pattern (prevents path traversal)
        raw_id = filtered.get("id", "")
        if not _ID_PATTERN.match(raw_id):
            filtered["id"] = re.sub(r"[^a-z0-9]+", "-", str(raw_id).lower()).strip("-")[:30]
            if not filtered["id"]:
                filtered["id"] = "invalid"

        # Sanitize string fields for safe Slack display (prevents mrkdwn injection from tampered JSON)
        for field in ("label", "category", "last_error"):
            if field in filtered and filtered[field]:
                filtered[field] = sanitize_slack_text(str(filtered[field]), max_length=200)

        # Clamp numeric fields to sensible bounds
        if "consecutive_failures" in filtered:
            filtered["consecutive_failures"] = max(
                0, min(int(filtered["consecutive_failures"]), 100)
            )
        if "event_count" in filtered:
            filtered["event_count"] = max(0, int(filtered["event_count"]))

        return cls(**filtered)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @property
    def cache_file(self) -> str:
        return os.path.join(ICS_CACHE_DIR, f"{self.id}_cache.json")

    @property
    def source_label(self) -> str:
        return f"ICS ({self.label})"


# ---- Client ----


class ICSFeedClient:
    """External ICS feed subscription manager with per-feed caching."""

    def __init__(self):
        self.subscriptions = self._load_subscriptions()

    # ---- Subscription CRUD ----

    def _load_subscriptions(self) -> List[ICSSubscription]:
        try:
            if os.path.exists(ICS_SUBSCRIPTIONS_FILE):
                with open(ICS_SUBSCRIPTIONS_FILE, "r") as f:
                    data = json.load(f)
                subs = []
                for s in data.get("subscriptions", []):
                    sub = ICSSubscription.from_dict(s)
                    # Validate URL on load — skip entries with tampered URLs
                    is_valid, _, _ = validate_ics_url(sub.url)
                    if not is_valid:
                        logger.warning(f"ICS: Skipping subscription '{sub.id}' with invalid URL")
                        continue
                    subs.append(sub)
                return subs
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"ICS: Failed to load subscriptions: {e}")
        return []

    def _save_subscriptions(self):
        try:
            os.makedirs(os.path.dirname(ICS_SUBSCRIPTIONS_FILE), exist_ok=True)
            data = {"version": 1, "subscriptions": [s.to_dict() for s in self.subscriptions]}
            tmp = ICS_SUBSCRIPTIONS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, ICS_SUBSCRIPTIONS_FILE)
        except OSError as e:
            logger.error(f"ICS: Failed to save subscriptions: {e}")

    def add_subscription(
        self, url: str, label: str, category: str = "Company", emoji: str = "📅", user_id: str = ""
    ) -> tuple:
        """Add a new subscription. Returns (success, message)."""
        if len(self.subscriptions) >= ICS_MAX_SUBSCRIPTIONS:
            return False, f"Maximum {ICS_MAX_SUBSCRIPTIONS} subscriptions reached"

        # Validate URL
        is_valid, result, _ = validate_ics_url(url)
        if not is_valid:
            return False, f"Invalid URL: {result}"
        url = result  # Use sanitized URL

        # Check for duplicate
        if any(s.url == url for s in self.subscriptions):
            return False, "This URL is already subscribed"

        # Generate ID from label
        sub_id = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:30]
        if any(s.id == sub_id for s in self.subscriptions):
            sub_id = f"{sub_id}-{len(self.subscriptions)}"

        sub = ICSSubscription(
            id=sub_id,
            url=url,
            label=label,
            category=category,
            emoji=emoji,
            added_by=user_id,
            added_at=datetime.now().isoformat(),
        )
        self.subscriptions.append(sub)
        self._save_subscriptions()

        # Initial fetch
        stats = self.refresh_subscription(sub.id, force=True)
        if stats.get("error"):
            return True, f"Subscription added but initial fetch failed: {stats['error']}"

        return True, f"Subscribed to *{label}* — {stats.get('event_count', 0)} events loaded"

    def remove_subscription(self, sub_id: str) -> tuple:
        """Remove a subscription. Returns (success, message)."""
        sub = next((s for s in self.subscriptions if s.id == sub_id), None)
        if not sub:
            return False, f"Subscription `{sub_id}` not found"

        self.subscriptions = [s for s in self.subscriptions if s.id != sub_id]
        self._save_subscriptions()

        # Clean up cache
        if os.path.exists(sub.cache_file):
            os.remove(sub.cache_file)

        return True, f"Removed subscription *{sub.label}*"

    def toggle_subscription(self, sub_id: str) -> tuple:
        """Toggle enabled state. Returns (success, message)."""
        sub = next((s for s in self.subscriptions if s.id == sub_id), None)
        if not sub:
            return False, f"Subscription `{sub_id}` not found"

        sub.enabled = not sub.enabled
        self._save_subscriptions()
        state = "✅ enabled" if sub.enabled else "❌ disabled"
        return True, f"*{sub.label}* is now {state}"

    def get_enabled_subscriptions(self) -> List[ICSSubscription]:
        return [s for s in self.subscriptions if s.enabled]

    # ---- Fetching & Parsing ----

    def refresh_subscription(self, sub_id: str, force: bool = False) -> dict:
        """Fetch and parse a single subscription. Returns stats dict."""
        sub = next((s for s in self.subscriptions if s.id == sub_id), None)
        if not sub:
            return {"error": "Not found"}

        if not force and self._is_cache_fresh(sub):
            return {"skipped": "Cache fresh"}

        try:
            content = self._fetch_ics(sub.url)
            events = self._parse_ics(content, sub)

            # Save cache
            cache = {
                "last_updated": datetime.now().isoformat(),
                "source_url": sub.url,
                "events": events,
            }
            self._save_cache(sub, cache)

            # Update subscription metadata
            sub.last_fetched = datetime.now().isoformat()
            sub.last_error = ""
            sub.event_count = len(events)
            sub.consecutive_failures = 0
            self._save_subscriptions()

            logger.info(f"ICS [{sub.id}]: Fetched {len(events)} events")
            return {"event_count": len(events)}

        except Exception as e:
            sub.consecutive_failures += 1
            sub.last_error = sanitize_slack_text(str(e), max_length=200)

            # Auto-disable after too many failures
            if sub.consecutive_failures >= ICS_MAX_CONSECUTIVE_FAILURES:
                sub.enabled = False
                logger.warning(
                    f"ICS [{sub.id}]: Auto-disabled after {sub.consecutive_failures} failures"
                )
                from slack.canvas import safe_record_warning

                safe_record_warning(f"ICS feed '{sub.label}' auto-disabled after repeated failures")

            self._save_subscriptions()
            logger.warning(f"ICS [{sub.id}]: Fetch failed: {e}")
            return {"error": sanitize_slack_text(str(e), max_length=200)}

    def refresh_all(self, force: bool = False) -> Dict[str, dict]:
        """Refresh all enabled subscriptions."""
        results = {}
        for sub in self.get_enabled_subscriptions():
            results[sub.id] = self.refresh_subscription(sub.id, force=force)
        return results

    def _fetch_ics(self, url: str) -> str:
        """Fetch ICS content from URL with size limit, DNS pinning, and redirect validation."""
        timeout = TIMEOUTS.get("http_request", 30)
        headers = {"User-Agent": "BrightDayBot/1.0"}

        for hop in range(_MAX_REDIRECTS + 1):
            # Validate URL and resolve DNS (single resolution per hop)
            is_valid, result, resolved_ip = validate_ics_url(url)
            if not is_valid:
                raise ValueError(f"URL validation failed: {result}")

            hostname = urlparse(url).hostname

            # Fetch with DNS pinned to validated IP (prevents DNS rebinding)
            resp = _fetch_with_pinned_dns(
                url,
                hostname,
                resolved_ip,
                timeout=timeout,
                headers=headers,
                stream=True,
                allow_redirects=False,
            )

            # Handle redirects: re-validate each hop
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    raise ValueError("Redirect with no Location header")
                url = urljoin(url, location)
                logger.debug(f"ICS: Following redirect to {url}")
                continue

            resp.raise_for_status()

            # Check size via Content-Length header
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > ICS_MAX_FILE_SIZE_BYTES:
                raise ValueError(f"Response too large: {content_length} bytes")

            # Read with streaming size limit
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=8192):
                total += len(chunk)
                if total > ICS_MAX_FILE_SIZE_BYTES:
                    raise ValueError(f"Response exceeds {ICS_MAX_FILE_SIZE_BYTES} byte limit")
                chunks.append(chunk)

            content = b"".join(chunks).decode("utf-8", errors="replace")

            if "BEGIN:VCALENDAR" not in content[:1000]:
                raise ValueError("Response is not a valid ICS calendar")

            return content

        raise ValueError(f"Too many redirects (max {_MAX_REDIRECTS})")

    def _parse_ics(self, content: str, sub: ICSSubscription) -> List[dict]:
        """Parse ICS content into event dicts for the current year."""
        import recurring_ical_events

        cal = Calendar.from_ical(content)
        current_year = datetime.now().year
        start = date(current_year, 1, 1)
        end = date(current_year, 12, 31)

        # Pre-screen: reject calendars with excessive raw events (DoS prevention)
        raw_vevent_count = sum(1 for _ in cal.walk("VEVENT"))
        if raw_vevent_count > ICS_MAX_EVENTS_PER_FEED * 8:
            logger.warning(f"ICS [{sub.id}]: Rejected calendar with {raw_vevent_count} raw VEVENTs")
            raise ValueError(
                f"Calendar has too many events ({raw_vevent_count}), max {ICS_MAX_EVENTS_PER_FEED * 8}"
            )

        # Pre-screen for dangerous high-frequency RRULEs (DoS prevention)
        for component in cal.walk("VEVENT"):
            rrule = component.get("RRULE")
            if rrule:
                freq = rrule.get("FREQ", [None])
                if freq and freq[0] in _DANGEROUS_RRULE_FREQS:
                    logger.warning(
                        f"ICS [{sub.id}]: Stripped high-frequency RRULE (FREQ={freq[0]})"
                    )
                    del component["RRULE"]

        # Expand recurring events for the current year
        expanded = recurring_ical_events.of(cal).between(start, end)

        events = []
        seen = set()

        # Iterate all expanded events, dedup, then cap
        for event in expanded:
            summary = str(event.get("SUMMARY", ""))
            if not summary:
                continue

            # Get date
            dtstart = event.get("DTSTART")
            if not dtstart:
                continue
            dt = dtstart.dt if hasattr(dtstart, "dt") else dtstart
            if isinstance(dt, datetime):
                dt = dt.date()
            if not isinstance(dt, date):
                continue

            dd_mm = dt.strftime("%d/%m")

            # Dedup within this feed (same name + date)
            key = (dd_mm, summary.lower())
            if key in seen:
                continue
            seen.add(key)

            description = str(event.get("DESCRIPTION", ""))
            event_url = str(event.get("URL", ""))

            # Validate event URL: HTTPS only, length cap, encode pipe for Slack mrkdwn safety
            if event_url and (
                not event_url.startswith("https://") or len(event_url) > _MAX_EVENT_URL_LENGTH
            ):
                event_url = ""
            elif event_url:
                event_url = event_url.replace("|", "%7C")

            events.append(
                {
                    "date": dd_mm,
                    "name": sanitize_for_prompt(summary, max_length=200),
                    "description": (
                        sanitize_for_prompt(description, max_length=500, allow_newlines=True)
                        if description
                        else ""
                    ),
                    "category": sub.category,
                    "emoji": sub.emoji,
                    "source": sub.source_label,
                    "url": event_url,
                }
            )

            if len(events) >= ICS_MAX_EVENTS_PER_FEED:
                logger.warning(
                    f"ICS [{sub.id}]: Truncated at {ICS_MAX_EVENTS_PER_FEED} events "
                    f"({len(expanded)} expanded)"
                )
                break

        return events

    # ---- Reading cached events ----

    def get_events_for_date(self, target_date) -> list:
        """Get SpecialDay objects from all enabled subscriptions for a date."""
        from storage.special_days import SpecialDay

        date_str = target_date.strftime("%d/%m")

        results = []
        for sub in self.get_enabled_subscriptions():
            cache = self._load_cache(sub)
            for ev in cache.get("events", []):
                if ev.get("date") == date_str:
                    results.append(
                        SpecialDay(
                            date=ev["date"],
                            name=ev["name"],
                            category=ev.get("category", sub.category),
                            description=ev.get("description", ""),
                            emoji=ev.get("emoji", sub.emoji),
                            enabled=True,
                            source=ev.get("source", sub.source_label),
                            url=ev.get("url", ""),
                        )
                    )
        return results

    def get_all_cached_special_days(self) -> list:
        """All cached events from all enabled subscriptions as SpecialDay objects."""
        from storage.special_days import SpecialDay

        results = []
        for sub in self.get_enabled_subscriptions():
            cache = self._load_cache(sub)
            for ev in cache.get("events", []):
                results.append(
                    SpecialDay(
                        date=ev["date"],
                        name=ev["name"],
                        category=ev.get("category", sub.category),
                        description=ev.get("description", ""),
                        emoji=ev.get("emoji", sub.emoji),
                        enabled=True,
                        source=ev.get("source", sub.source_label),
                        url=ev.get("url", ""),
                    )
                )
        return results

    def preview_feed(self, url: str) -> dict:
        """Preview a feed without subscribing. Returns summary."""
        is_valid, result, _ = validate_ics_url(url)
        if not is_valid:
            return {"error": result}

        try:
            content = self._fetch_ics(result)
            dummy_sub = ICSSubscription(id="preview", url=result, label="Preview")
            events = self._parse_ics(content, dummy_sub)
            return {
                "event_count": len(events),
                "sample": events[:5],
            }
        except Exception as e:
            return {"error": sanitize_slack_text(str(e), max_length=200)}

    # ---- Cache I/O ----

    def _load_cache(self, sub: ICSSubscription) -> dict:
        if not os.path.exists(sub.cache_file):
            return {"events": []}
        try:
            with open(sub.cache_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"events": []}

    def _save_cache(self, sub: ICSSubscription, cache: dict):
        try:
            os.makedirs(os.path.dirname(sub.cache_file), exist_ok=True)
            tmp = sub.cache_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            os.replace(tmp, sub.cache_file)
        except OSError as e:
            logger.warning(f"ICS [{sub.id}]: Failed to save cache: {e}")

    def _is_cache_fresh(self, sub: ICSSubscription) -> bool:
        cache = self._load_cache(sub)
        last = cache.get("last_updated")
        if not last:
            return False
        try:
            age = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 86400
            return age < ICS_CACHE_TTL_DAYS
        except (ValueError, TypeError):
            return False

    # ---- Status ----

    def get_status(self) -> dict:
        """Aggregate status for canvas/admin display."""
        total_events = 0
        all_fresh = True
        last_updated = None

        for sub in self.get_enabled_subscriptions():
            total_events += sub.event_count
            if not self._is_cache_fresh(sub):
                all_fresh = False
            if sub.last_fetched:
                if last_updated is None or sub.last_fetched > last_updated:
                    last_updated = sub.last_fetched

        return {
            "enabled": ICS_SUBSCRIPTIONS_ENABLED,
            "subscription_count": len(self.subscriptions),
            "enabled_count": len(self.get_enabled_subscriptions()),
            "total_events": total_events,
            "all_fresh": all_fresh,
            "last_updated": last_updated,
            "subscriptions": [
                {
                    "id": s.id,
                    "label": s.label,
                    "enabled": s.enabled,
                    "event_count": s.event_count,
                    "cache_fresh": self._is_cache_fresh(s),
                    "last_fetched": s.last_fetched,
                    "last_error": s.last_error,
                }
                for s in self.subscriptions
            ],
        }
