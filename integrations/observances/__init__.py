"""
Observance sources registry.

Centralizes the list of observance sources (UN, UNESCO, WHO) so that
consumers (scheduler, admin commands, cache init) can iterate over
enabled sources without duplicating the source list.
"""

from config import (
    UN_OBSERVANCES_ENABLED,
    UNESCO_OBSERVANCES_ENABLED,
    WHO_OBSERVANCES_ENABLED,
)


def get_enabled_sources():
    """
    Return (name, refresh_fn, status_fn) for each enabled observance source.

    Imports are deferred to avoid circular dependencies and to skip
    loading modules for disabled sources.
    """
    sources = []

    if UN_OBSERVANCES_ENABLED:
        from integrations.observances.un import get_un_cache_status, refresh_un_cache

        sources.append(("UN", refresh_un_cache, get_un_cache_status))

    if UNESCO_OBSERVANCES_ENABLED:
        from integrations.observances.unesco import (
            get_unesco_cache_status,
            refresh_unesco_cache,
        )

        sources.append(("UNESCO", refresh_unesco_cache, get_unesco_cache_status))

    if WHO_OBSERVANCES_ENABLED:
        from integrations.observances.who import (
            get_who_cache_status,
            refresh_who_cache,
        )

        sources.append(("WHO", refresh_who_cache, get_who_cache_status))

    return sources
