"""Sanitize once; derive text and mentions only from the stored safe HTML."""

from uuid import UUID

import nh3
from bs4 import BeautifulSoup

TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "u",
    "s",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "a",
    "span",
    "mention-component",
}
ATTRIBUTES = {
    "a": {"href", "title"},
    "span": {"data-type", "data-id"},
    "mention-component": {"data-id", "entity_name", "entity_identifier"},
}


def clean_content(value):
    html = nh3.clean(
        value, tags=TAGS, attributes=ATTRIBUTES, url_schemes={"http", "https", "mailto"}
    )
    soup = BeautifulSoup(html, "html.parser")
    mentions = set()
    for tag in soup.select(
        "mention-component[data-id], "
        'mention-component[entity_name="user_mention"][entity_identifier], '
        'span[data-type="mention"][data-id]'
    ):
        try:
            mentions.add(UUID(tag.get("data-id") or tag.get("entity_identifier")))
        except (ValueError, TypeError, AttributeError):
            tag.attrs.clear()
    return str(soup), soup.get_text(" ", strip=True), mentions
