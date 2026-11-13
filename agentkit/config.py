"""Leitura, gravação e mescla do agentkit.yaml de cada projeto."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .defaults import AGENTS, default_config

CONFIG_FILE = "agentkit.yaml"
RECENT_FILE = Path.home() / ".agentkit" / "recent.json"


def deep_merge(base: dict, override: dict) -> dict:
    """Mescla recursiva: o que vem em `override` vence; listas são substituídas."""
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def normalize(cfg: dict) -> dict:
    """Garante que todas as chaves e todos os agentes existam."""
    cfg = deep_merge(default_config(), cfg or {})
    for name, meta in AGENTS.items():
        agent = cfg["agents"].setdefault(name, {})
        agent.setdefault("enabled", True)
        agent.setdefault("model", meta["default_model"])
        agent.setdefault("extra_instructions", "")
    # agentes desconhecidos (versões antigas) são descartados
    cfg["agents"] = {k: v for k, v in cfg["agents"].items() if k in AGENTS}
    return cfg


def config_path(project: str | Path) -> Path:
    return Path(project).expanduser().resolve() / CONFIG_FILE


def load(project: str | Path) -> dict | None:
    path = config_path(project)
    if not path.exists():
        return None
    return normalize(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def save(project: str | Path, cfg: dict) -> Path:
    path = config_path(project)
    header = (
        "# Configuração do AgentKit para este projeto.\n"
        "# Edite pela interface (agentkit gui) ou à mão e rode `agentkit install`.\n"
    )
    body = yaml.safe_dump(normalize(cfg), sort_keys=False, allow_unicode=True, width=100)
    path.write_text(header + body, encoding="utf-8")
    remember(project, cfg.get("project", {}).get("name", ""))
    return path


def remember(project: str | Path, name: str = "") -> None:
    """Guarda a lista de projetos recentes para a interface."""
    project = str(Path(project).expanduser().resolve())
    try:
        RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        items = json.loads(RECENT_FILE.read_text(encoding="utf-8")) if RECENT_FILE.exists() else []
    except (OSError, json.JSONDecodeError):
        items = []
    items = [i for i in items if i.get("path") != project]
    items.insert(0, {"path": project, "name": name or Path(project).name})
    try:
        RECENT_FILE.write_text(json.dumps(items[:15], indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def recent() -> list[dict]:
    try:
        items = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [i for i in items if Path(i["path"]).exists()]
