"""Architecture checks for the standalone extraction."""

from pathlib import Path

import gitscience


def test_core_has_no_physics_intern_or_kwant_package_imports():
    core = Path(gitscience.__file__).parent
    sources = "\n".join(path.read_text() for path in core.glob("*.py"))

    assert "physics_intern" not in sources
    assert "import gitscience_kwant" not in sources
    assert "from gitscience_kwant" not in sources


def test_physics_intern_is_confined_to_optional_adapter():
    core = Path(gitscience.__file__).parent
    sources = "\n".join(path.read_text() for path in core.glob("*.py"))

    assert "import physics_intern" not in sources
    assert "from physics_intern" not in sources
