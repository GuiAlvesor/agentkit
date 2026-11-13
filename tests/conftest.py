import pytest

from agentkit import config as cfgmod


@pytest.fixture(autouse=True)
def isolated_recent(tmp_path_factory, monkeypatch):
    """Não suja a lista de projetos recentes do usuário durante os testes."""
    monkeypatch.setattr(cfgmod, "RECENT_FILE", tmp_path_factory.mktemp("home") / "recent.json")
