"""Small HTML helpers for the server pages."""
import json
import html as _html


def _esc(value: object, quote: bool = True) -> str:
    return _html.escape(str(value or ""), quote=quote)


def _js_arg(value: str | None) -> str:
    """Encode a string for a quoted inline handler without breaking the page."""
    return _esc(json.dumps(value or ""), quote=True)


def _url_link(url: str | None) -> str:
    """The server's URL as a new-tab link; plain text unless it is http(s)."""
    if not (url or "").lower().startswith(("http://", "https://")):
        return _esc(url)
    return f'<a href="{_esc(url)}" target="_blank" rel="noopener noreferrer">{_esc(url)}</a>'


def _format_dt(value: object, fmt: str, fallback: str = "never") -> str:
    if not value:
        return fallback
    formatter = getattr(value, "strftime", None)
    return formatter(fmt) if formatter else _esc(value)
