"""CLAUDE.md: deal_recommendation may import exactly one module from iron_bank."""

import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[2] / "app" / "deal_recommendation"
ALLOWED = {"app.iron_bank.services.deal_catalog_service"}
OTHER_DOMAINS = ("app.iron_bank", "app.markets", "app.users", "app.zillow", "app.external_api")


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


def test_only_the_catalog_facade_is_imported_from_other_domains():
    offenders = {
        f"{path.relative_to(DOMAIN)}: {module}"
        for path in DOMAIN.rglob("*.py")
        for module in _imports(path)
        if module.startswith(OTHER_DOMAINS) and module not in ALLOWED
    }
    assert offenders == set()
