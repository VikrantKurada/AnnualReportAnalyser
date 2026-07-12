from dataclasses import dataclass, field


@dataclass
class ParsedDoc:
    """Normalized document: ordered sections and extracted tables."""
    sections: list[dict] = field(default_factory=list)  # {"title","text","page"}
    tables: list[dict] = field(default_factory=list)    # {"caption","rows","page","section"}
