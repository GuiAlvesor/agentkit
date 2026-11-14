"""Detecção automática da stack de um diretório, para pré-preencher a configuração."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


def _git_base_branch(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        )
        if out.returncode == 0 and "/" in out.stdout:
            return out.stdout.strip().split("/", 1)[1]
        out = subprocess.run(
            ["git", "branch", "--list", "main", "master", "develop"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        )
        names = [b.strip(" *") for b in out.stdout.splitlines() if b.strip()]
        for candidate in ("main", "master", "develop"):
            if candidate in names:
                return candidate
    except (OSError, subprocess.SubprocessError):
        pass
    return "main"


def _node(root: Path, result: dict) -> None:
    pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    scripts = pkg.get("scripts", {})
    pm = "npm"
    if (root / "pnpm-lock.yaml").exists():
        pm = "pnpm"
    elif (root / "yarn.lock").exists():
        pm = "yarn"
    elif (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        pm = "bun"
    # sempre "<pm> run <script>": evita colidir com comandos nativos (ex.: `pnpm deploy`)
    run = lambda s: f"{pm} run {s}"

    result["language"] = "typescript" if "typescript" in deps or (root / "tsconfig.json").exists() else "javascript"
    for fw in ("next", "react", "vue", "svelte", "@angular/core", "express", "fastify", "@nestjs/core", "vite"):
        if fw in deps:
            result["frameworks"].append(fw.replace("@angular/core", "angular").replace("@nestjs/core", "nestjs"))
    cmds = result["commands"]
    cmds["install"] = f"{pm} install"
    if "test" in scripts:
        cmds["test"] = f"{pm} test" if pm != "bun" else "bun run test"
    for key, names in {"lint": ["lint"], "typecheck": ["typecheck", "type-check", "tsc"], "build": ["build"]}.items():
        for n in names:
            if n in scripts:
                cmds[key] = run(n)
                break
    if not cmds["typecheck"] and result["language"] == "typescript":
        cmds["typecheck"] = "npx tsc --noEmit"
    for n in ("deploy:staging", "deploy-staging"):
        if n in scripts:
            cmds["deploy_staging"] = run(n)
    for n in ("deploy", "deploy:prod", "deploy:production"):
        if n in scripts:
            cmds["deploy_production"] = run(n)


def _python(root: Path, result: dict) -> None:
    result["language"] = "python"
    text = ""
    for f in ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "setup.cfg", "Pipfile"):
        if (root / f).exists():
            text += (root / f).read_text(encoding="utf-8", errors="ignore").lower()
    for fw in ("django", "fastapi", "flask", "streamlit", "pandas"):
        if fw in text:
            result["frameworks"].append(fw)
    cmds = result["commands"]
    prefix = ""
    if (root / "uv.lock").exists():
        cmds["install"], prefix = "uv sync", "uv run "
    elif (root / "poetry.lock").exists():
        cmds["install"], prefix = "poetry install", "poetry run "
    elif (root / "requirements.txt").exists():
        cmds["install"] = "pip install -r requirements.txt"
    elif (root / "pyproject.toml").exists():
        # com extra "dev" (onde costuma estar o pytest), instala junto para os testes rodarem
        has_dev = re.search(r"^\s*dev\s*=", text, re.M) and "optional-dependencies" in text
        cmds["install"] = 'pip install -e ".[dev]"' if has_dev else "pip install -e ."
    if "pytest" in text or (root / "tests").exists():
        cmds["test"] = f"{prefix}pytest"
    if "ruff" in text:
        cmds["lint"] = f"{prefix}ruff check ."
    elif "flake8" in text:
        cmds["lint"] = f"{prefix}flake8"
    if "mypy" in text:
        cmds["typecheck"] = f"{prefix}mypy ."
    elif "pyright" in text:
        cmds["typecheck"] = f"{prefix}pyright"
    if "django" in result["frameworks"] and not cmds["test"]:
        cmds["test"] = f"{prefix}python manage.py test"


def _makefile_targets(root: Path) -> set[str]:
    mk = root / "Makefile"
    if not mk.exists():
        return set()
    return set(re.findall(r"^([A-Za-z0-9_.-]+):", mk.read_text(encoding="utf-8", errors="ignore"), re.M))


def detect(path: str | Path) -> dict:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Diretório não encontrado: {root}")

    result: dict = {
        "name": root.name,
        "language": "",
        "frameworks": [],
        "base_branch": _git_base_branch(root),
        "is_git": (root / ".git").exists(),
        "has_claude_dir": (root / ".claude").exists(),
        "has_claude_md": (root / "CLAUDE.md").exists(),
        "signals": [],
        "commands": {k: "" for k in (
            "install", "test", "lint", "typecheck", "build",
            "deploy_staging", "deploy_production", "health_check", "rollback",
        )},
    }
    cmds = result["commands"]

    if (root / "package.json").exists():
        result["signals"].append("package.json")
        try:
            _node(root, result)
        except (json.JSONDecodeError, OSError):
            pass
    if any((root / f).exists() for f in ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "manage.py")):
        result["signals"].append("python")
        if not result["language"]:
            _python(root, result)
    if (root / "go.mod").exists():
        result["signals"].append("go.mod")
        result["language"] = result["language"] or "go"
        cmds.update({k: v for k, v in {"install": "go mod download", "test": "go test ./...",
                                         "lint": "go vet ./...", "build": "go build ./..."}.items() if not cmds[k]})
    if (root / "Cargo.toml").exists():
        result["signals"].append("Cargo.toml")
        result["language"] = result["language"] or "rust"
        cmds.update({k: v for k, v in {"test": "cargo test", "lint": "cargo clippy -- -D warnings",
                                         "build": "cargo build --release"}.items() if not cmds[k]})
    if (root / "pom.xml").exists():
        result["signals"].append("pom.xml")
        result["language"] = result["language"] or "java"
        mvn = "./mvnw" if (root / "mvnw").exists() else "mvn"
        cmds.update({k: v for k, v in {"test": f"{mvn} test", "build": f"{mvn} package -DskipTests"}.items() if not cmds[k]})
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        result["signals"].append("gradle")
        result["language"] = result["language"] or "kotlin/java"
        gw = "./gradlew" if (root / "gradlew").exists() else "gradle"
        cmds.update({k: v for k, v in {"test": f"{gw} test", "build": f"{gw} build -x test"}.items() if not cmds[k]})
    if any(root.glob("*.csproj")) or any(root.glob("*.sln")):
        result["signals"].append(".NET")
        result["language"] = result["language"] or "csharp"
        cmds.update({k: v for k, v in {"test": "dotnet test", "build": "dotnet build"}.items() if not cmds[k]})

    targets = _makefile_targets(root)
    if targets:
        result["signals"].append("Makefile")
        for key, names in {"test": ["test"], "lint": ["lint"], "build": ["build"],
                           "deploy_staging": ["deploy-staging", "deploy_staging", "staging"],
                           "deploy_production": ["deploy", "deploy-prod", "release"]}.items():
            for n in names:
                if n in targets and not cmds[key]:
                    cmds[key] = f"make {n}"
                    break

    for f in ("Dockerfile", "docker-compose.yml", "compose.yaml", "vercel.json", "netlify.toml",
              "fly.toml", "serverless.yml", "Chart.yaml", "k8s", "terraform"):
        if (root / f).exists():
            result["signals"].append(f)
    if (root / "fly.toml").exists() and not cmds["deploy_production"]:
        cmds["deploy_production"] = "fly deploy"
    if (root / "vercel.json").exists() and not cmds["deploy_production"]:
        cmds["deploy_production"], cmds["deploy_staging"] = "vercel --prod", cmds["deploy_staging"] or "vercel"

    result["frameworks"] = sorted(set(result["frameworks"]))
    return result
