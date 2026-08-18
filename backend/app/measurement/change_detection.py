from dataclasses import dataclass, field


@dataclass
class ChangeSet:
    """Structured diff between two PageObservation.normalized_extraction
    snapshots (Group F2) — reuses the shape crawler/extract.py already
    produces (title/h1/json_ld/internal_links/content_hash), no new
    extraction code needed."""

    page_created: bool = False
    title_changed: bool = False
    h1_changed: bool = False
    text_changed: bool = False
    links_added: list[str] = field(default_factory=list)
    schema_added: bool = False

    def has_meaningful_change(self) -> bool:
        return (
            self.page_created
            or self.title_changed
            or self.h1_changed
            or self.text_changed
            or bool(self.links_added)
            or self.schema_added
        )


def compare_page_states(before: dict | None, after: dict) -> ChangeSet:
    if not before:
        return ChangeSet(page_created=True)

    before_links = set(before.get("internal_links") or [])
    after_links = set(after.get("internal_links") or [])

    return ChangeSet(
        page_created=False,
        title_changed=(before.get("title") or "") != (after.get("title") or ""),
        h1_changed=(before.get("h1") or "") != (after.get("h1") or ""),
        text_changed=(before.get("content_hash") or "") != (after.get("content_hash") or ""),
        links_added=sorted(after_links - before_links),
        schema_added=len(after.get("json_ld") or []) > len(before.get("json_ld") or []),
    )
