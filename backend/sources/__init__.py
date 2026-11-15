"""Live data sources. Each module fetches and normalises; nothing here touches the database."""


class SourceError(RuntimeError):
    """A live source could not be reached or returned something we could not read."""
