from dataclasses import dataclass, field


@dataclass
class Item:
    url: str
    title: str
    source: str
    published: float | None  # unix timestamp, None if the feed gave no date
    lead: str
    weight: float = 1.0
    ai_only: bool = True
    text: str = ""
    score: int = 0
    category: str = ""
    reason: str = ""
    summary: dict = field(default_factory=dict)
    also: list["Item"] = field(default_factory=list)  # other outlets covering the same story
