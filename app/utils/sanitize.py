

import re
from html.parser import HTMLParser
from typing import List, Optional, Tuple

# Matches any HTML/XML-style tag, e.g. <script>, </b>, <img src=x onerror=..>,
# including self-closing and attribute-bearing variants.
_HTML_TAG_PATTERN = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")

# Common HTML entities / javascript: pseudo-protocol used to smuggle markup
# or script execution past a naive "no angle brackets" check.
_SUSPICIOUS_MARKUP_PATTERN = re.compile(
    r"&#x?[0-9a-fA-F]+;|javascript\s*:", re.IGNORECASE
)

NO_HTML_MESSAGE = "HTML or script tags are not allowed."


def contains_html(value: Optional[str]) -> bool:
    """Return True if `value` contains anything that looks like an HTML/XML
    tag or a common obfuscation of one (HTML entities, javascript: URIs)."""
    if not value:
        return False
    return bool(_HTML_TAG_PATTERN.search(value)) or bool(
        _SUSPICIOUS_MARKUP_PATTERN.search(value)
    )


def reject_html(value: Optional[str]) -> Optional[str]:
    """Validator helper: raise ValueError if `value` contains HTML/script
    markup, otherwise return it unchanged."""
    if contains_html(value):
        raise ValueError(NO_HTML_MESSAGE)
    return value


# ─────────────────────────────────────────────
# Rich-text allowlist sanitizer
#
# Mirrors the frontend's sanitizeRichHtml (components/resume-builder/
# richTextFormat.jsx) tag-for-tag and attribute-for-attribute, so a field
# that's genuinely meant to carry WYSIWYG formatting (Job Description, Project
# Description -- edited via the RichTextArea toolbar, not a plain textarea)
# can accept the same small bold/italic/underline/list/link/alignment
# allowlist the editor itself produces, instead of reject_html's blanket
# "no tags at all" rule, which was written for plain-text fields and
# rejects even the WYSIWYG editor's own legitimate output.
#
# This runs server-side as the authoritative check -- the frontend's own
# sanitizeRichHtml is defense in depth on top of this, not a substitute
# for it, the same way client-side validation never is.
# ─────────────────────────────────────────────

_RICH_TEXT_ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ul", "ol", "li", "br", "div", "p", "span", "a",
}
_RICH_TEXT_STYLE_TAGS = {"div", "p", "span"}
_RICH_TEXT_ALLOWED_ALIGNMENTS = {"left", "center", "right", "justify"}
_RICH_TEXT_SAFE_URL = re.compile(r"^(https?:|mailto:)", re.IGNORECASE)
_TEXT_ALIGN_PATTERN = re.compile(r"text-align\s*:\s*([a-z]+)", re.IGNORECASE)

_VOID_TAGS = {"br"}


def _extract_safe_text_align(style_attr: Optional[str]) -> Optional[str]:
    if not style_attr:
        return None
    match = _TEXT_ALIGN_PATTERN.search(style_attr)
    if not match:
        return None
    value = match.group(1).lower()
    return value if value in _RICH_TEXT_ALLOWED_ALIGNMENTS else None


class _RichTextSanitizer(HTMLParser):
    """Rebuilds the input as an allowlisted-safe HTML string. Anything not
    on the allowlist is unwrapped (children kept, the tag itself dropped)
    rather than deleted outright -- same "degrade to plain text" behaviour
    as the frontend sanitizer, so a stray/unsupported tag can't silently
    eat content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out: List[str] = []
        # Stack of booleans: whether the currently-open tag at each depth
        # was allowed (and so needs its closing tag emitted too).
        self._stack: List[Tuple[str, bool]] = []

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs, self_closing=True)

    def _open(self, tag, attrs, self_closing):
        tag = tag.lower()
        if tag not in _RICH_TEXT_ALLOWED_TAGS:
            if not self_closing:
                self._stack.append((tag, False))
            return

        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        rendered_attrs = ""
        if tag == "a":
            href = attr_dict.get("href", "").strip()
            if _RICH_TEXT_SAFE_URL.match(href):
                safe_href = href.replace('"', "&quot;")
                rendered_attrs = f' href="{safe_href}" target="_blank" rel="noopener noreferrer"'
        if tag in _RICH_TEXT_STYLE_TAGS:
            align = _extract_safe_text_align(attr_dict.get("style"))
            if align:
                rendered_attrs += f' style="text-align:{align}"'

        if tag in _VOID_TAGS or self_closing:
            self._out.append(f"<{tag}{rendered_attrs}>")
        else:
            self._out.append(f"<{tag}{rendered_attrs}>")
            self._stack.append((tag, True))

    def handle_endtag(self, tag):
        tag = tag.lower()
        # Pop the matching open tag off the stack, regardless of what else
        # is on top of it (mirrors how browsers -- and the frontend's
        # DOMParser-based sanitizer -- recover from mismatched markup
        # instead of erroring out on it).
        for i in range(len(self._stack) - 1, -1, -1):
            open_tag, allowed = self._stack[i]
            if open_tag == tag:
                if allowed:
                    self._out.append(f"</{tag}>")
                del self._stack[i:]
                return
        # No matching open tag found -- ignore, same as a browser would.

    def handle_data(self, data):
        self._out.append(
            data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

    def get_html(self) -> str:
        # Close out anything left open (malformed input with no closing tag).
        while self._stack:
            open_tag, allowed = self._stack.pop()
            if allowed:
                self._out.append(f"</{open_tag}>")
        return "".join(self._out)


def sanitize_rich_html(value: Optional[str]) -> Optional[str]:
    """Strips `value` down to the small bold/italic/underline/list/link/
    alignment allowlist the RichTextArea WYSIWYG editor produces (see the
    module docstring above). Returns None for empty/None input so callers
    can keep treating "no value" consistently with the rest of this file.
    """
    if not value:
        return None
    parser = _RichTextSanitizer()
    parser.feed(value)
    parser.close()
    cleaned = parser.get_html()
    return cleaned or None


def rich_text_plain_length(value: Optional[str]) -> int:
    """Word count of `value` with tags stripped, matching the frontend's
    htmlToPlainText-based countWords -- so a 200-word cap counts actual
    words, not HTML tags, once these fields carry real markup."""
    if not value:
        return 0
    plain = re.sub(r"<[^>]*>", " ", value)
    plain = plain.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return len(plain.split())