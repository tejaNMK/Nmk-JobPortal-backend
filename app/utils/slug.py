from __future__ import annotations

import re


_non_alnum_re = re.compile(r"[^a-z0-9]+")


def slugify_job_title(title: str) -> str:


    if title is None:
        title = ""

    s = str(title).strip().lower()
    s = _non_alnum_re.sub("-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s

