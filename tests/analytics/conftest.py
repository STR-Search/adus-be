from types import SimpleNamespace

from sqlalchemy.dialects import postgresql


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]

    def scalar_one(self):
        return self._rows[0][0]


class CapturingDb:
    """Records every query; answers each with the next queued row set."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return FakeResult(self.responses.pop(0) if self.responses else [])


def row(**values):
    """A result row that unpacks like a tuple and exposes ``_mapping``."""
    return _Row(values)


class _Row(tuple):
    def __new__(cls, values):
        instance = super().__new__(cls, values.values())
        instance._mapping = values
        return instance


def sql(query) -> str:
    return str(
        query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def market(id, name):
    return SimpleNamespace(id=id, market_name=name)
