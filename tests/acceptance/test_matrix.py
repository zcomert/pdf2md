import ast
from pathlib import Path

from tests.acceptance.criteria import CRITERIA

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {str(n) for n in range(1, 29)} | {f"G{n}" for n in range(1, 6)}


def test_every_criterion_is_mapped():
    assert set(CRITERIA) == EXPECTED
    assert all(nodes for _, nodes in CRITERIA.values())


def test_every_mapped_test_exists():
    """Matris çürümesin: eşlenen her test dosyası ve fonksiyonu gerçekten var."""
    functions = {}
    missing = []
    for _, nodes in CRITERIA.values():
        for node in nodes:
            path, name = node.split("::")
            if path not in functions:
                tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
                functions[path] = {item.name for item in ast.walk(tree) if isinstance(item, ast.FunctionDef)}
            if name not in functions[path]:
                missing.append(node)
    assert not missing, missing
