"""Public facade for web discovery, safe fetching, and source import."""

from .fetch import (
    WebFetchError,
    WebFetchSecurityError,
    fetch_web_page,
    normalize_web_url,
    validate_public_web_url,
)
from .search import (
    WebSearchConfigurationError,
    WebSearchRequestError,
    available_web_search_providers,
    search_web,
)
from .sources import (
    delete_imported_web_pages,
    get_imported_web_pages_retrieval_statuses,
    import_fetched_web_pages,
    load_imported_web_page,
    set_imported_web_pages_retrieval_status,
)

__all__ = [
    "WebFetchError",
    "WebFetchSecurityError",
    "WebSearchConfigurationError",
    "WebSearchRequestError",
    "available_web_search_providers",
    "fetch_web_page",
    "delete_imported_web_pages",
    "get_imported_web_pages_retrieval_statuses",
    "import_fetched_web_pages",
    "load_imported_web_page",
    "set_imported_web_pages_retrieval_status",
    "normalize_web_url",
    "search_web",
    "validate_public_web_url",
]
