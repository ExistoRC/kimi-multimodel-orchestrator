from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
KIMI_HOME = Path(os.environ.get("KIMI_CODE_HOME") or (Path.home() / ".kimi-code"))
DATA_DIR = KIMI_HOME / "multimodel-orchestrator"
ROUTING_FILE = KIMI_HOME / "multimodel-orchestrator.routing.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
RUNTIME_FILE = DATA_DIR / "runtime.json"
DEFAULT_SETTINGS = {
    "auto_start": True,
    "always_on_top": True,
    "opacity": 0.97,
    "width": 460,
    "height": 590,
    "position": None,
    "language": "zh-CN",
}
MODE_TIERS = {
    "single": ("L1",),
    "two-tier": ("L1", "L2"),
    "modality": ("any",),
    "auto": ("L1", "L2", "L3"),
}
MODALITIES = ("text", "image", "video")
SAVE_LOCK = threading.Lock()


def routing_tiers(routing: dict[str, Any]) -> tuple[str, ...]:
    version = routing.get("version")
    if version == 1:
        return ("L1", "L2", "L3")
    if version != 2:
        raise ValueError("路由配置 version 必须为 1 或 2")
    mode = routing.get("mode")
    if mode not in MODE_TIERS:
        raise ValueError("version 2 路由的 mode 必须为 single、two-tier、modality 或 auto")
    return MODE_TIERS[mode]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def load_settings() -> dict[str, Any]:
    try:
        stored = read_json(SETTINGS_FILE)
    except FileNotFoundError:
        stored = {}
    settings = {**DEFAULT_SETTINGS, **stored}
    settings["auto_start"] = bool(settings["auto_start"])
    settings["always_on_top"] = bool(settings["always_on_top"])
    settings["opacity"] = min(1.0, max(0.65, float(settings["opacity"])))
    settings["width"] = min(720, max(400, int(settings["width"])))
    settings["height"] = min(900, max(480, int(settings["height"])))
    if settings.get("language") not in {"zh-CN", "en"}:
        settings["language"] = "zh-CN"
    position = settings.get("position")
    if not (isinstance(position, list) and len(position) == 2 and all(isinstance(v, (int, float)) for v in position)):
        settings["position"] = None
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    atomic_json(SETTINGS_FILE, settings)


def load_routing() -> dict[str, Any]:
    try:
        return read_json(ROUTING_FILE)
    except FileNotFoundError:
        return read_json(PLUGIN_ROOT / "routing.json")


def model_catalog() -> dict[str, Any]:
    config_path = KIMI_HOME / "config.toml"
    with config_path.open("rb") as handle:
        config = tomllib.load(handle)
    pool = list(config.get("secondary_model", {}).get("models", {}).keys())
    models = {}
    for alias, entry in config.get("models", {}).items():
        models[alias] = {
            "model": entry.get("model", alias),
            "display_name": entry.get("display_name", alias),
            "capabilities": list(entry.get("capabilities", [])),
        }
    return {
        "main_model": config.get("default_model", "未配置"),
        "pool": pool,
        "available": list(models.keys()),
        "models": models,
    }


def validate_routing(routing: dict[str, Any], catalog: dict[str, Any]) -> None:
    tiers = routing_tiers(routing)
    if not isinstance(routing.get("managedAgents"), dict) or not routing["managedAgents"]:
        raise ValueError("managedAgents 不能为空")
    if not isinstance(routing.get("models"), dict):
        raise ValueError("models 必须是对象")
    route_tables = [routing.get("routes")]
    if routing.get("mode") == "auto" and "autoRoutes" in routing:
        route_tables.append(routing["autoRoutes"])
    if any(not isinstance(routes, dict) for routes in route_tables):
        raise ValueError("routes/autoRoutes 必须是对象")
    available = set(catalog["available"])
    for routes in route_tables:
        for tier in tiers:
            for modality in MODALITIES:
                alias = routes.get(tier, {}).get(modality)
                if alias not in available:
                    raise ValueError(f"{tier}/{modality} 的模型 {alias or '未设置'} 不在模型库中")
                if alias not in routing["models"]:
                    raise ValueError(f"模型 {alias} 缺少 modalities 声明")
                declared = routing["models"][alias].get("modalities", [])
                if not isinstance(declared, list) or modality not in declared:
                    raise ValueError(f"模型 {alias} 的路由声明不支持 {modality}")
                capabilities = catalog["models"].get(alias, {}).get("capabilities", [])
                if "tool_use" not in capabilities:
                    raise ValueError(f"模型 {alias} 未声明支持子代理所需的 tool_use")
                required = {"image": "image_in", "video": "video_in"}.get(modality)
                if required and required not in capabilities:
                    raise ValueError(f"模型 {alias} 的实际配置不支持 {modality}")


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _insert_pool_entries(text: str, aliases: list[str], catalog: dict[str, Any], current_default: str) -> str:
    entries = "".join(
        f"{_toml_string(alias)} = {_toml_string(catalog['models'][alias]['display_name'] + '（由悬浮窗加入子代理池）')}\n"
        for alias in aliases
    )
    lines = text.splitlines(keepends=True)
    secondary_header = next((index for index, line in enumerate(lines) if line.strip() == "[secondary_model]"), None)
    if secondary_header is None:
        text = text.rstrip() + f"\n\n[secondary_model]\ndefault_model = {_toml_string(current_default or aliases[0])}\n"
        lines = text.splitlines(keepends=True)
    elif not current_default:
        lines.insert(secondary_header + 1, f"default_model = {_toml_string(aliases[0])}\n")
    text = "".join(lines)
    pool_header = next((index for index, line in enumerate(lines) if line.strip() == "[secondary_model.models]"), None)
    if pool_header is not None:
        lines.insert(pool_header + 1, entries)
        return "".join(lines)
    suffix = "" if text.endswith("\n") else "\n"
    return text + suffix + "\n[secondary_model.models]\n" + entries


def _doctor(candidate: Path) -> None:
    kimi = shutil.which("kimi")
    if kimi:
        command = [kimi, "doctor", "config", str(candidate)]
        env = os.environ.copy()
    else:
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if not npx:
            raise ValueError("找不到 kimi doctor 或 npx，未修改模型池配置")
        command = [npx, "--yes", "@moonshot-ai/kimi-code@2.5.3", "doctor", "config", str(candidate)]
        env = {**os.environ, "npm_config_cache": os.environ.get("npm_config_cache", str(DATA_DIR / "npm-cache"))}
    result = subprocess.run(command, cwd=KIMI_HOME, env=env, capture_output=True, timeout=180)
    if result.returncode != 0:
        raise ValueError("kimi doctor 校验未通过，原配置未修改；请手动运行 doctor 查看原因")


def ensure_pool_aliases(aliases: list[str], catalog: dict[str, Any]) -> Path | None:
    missing = list(dict.fromkeys(alias for alias in aliases if alias not in catalog["pool"]))
    if not missing:
        return None
    config_path = KIMI_HOME / "config.toml"
    original_text = config_path.read_text(encoding="utf-8")
    original = tomllib.loads(original_text)
    for alias in missing:
        if alias not in original.get("models", {}):
            raise ValueError(f"模型 {alias} 不在模型库中，未修改配置")
    current_default = original.get("secondary_model", {}).get("default_model", "")
    updated_text = _insert_pool_entries(original_text, missing, catalog, current_default)
    updated = tomllib.loads(updated_text)
    for key, value in original.items():
        if key == "secondary_model":
            for alias, hint in value.get("models", {}).items():
                assert updated[key]["models"][alias] == hint
        else:
            assert updated[key] == value, key
    candidate = KIMI_HOME / "config-multimodel-new.toml"
    if candidate.exists():
        raise ValueError("config-multimodel-new.toml 已存在，未覆盖；请检查后重试")
    backup = None
    try:
        candidate.write_text(updated_text, encoding="utf-8", newline="\n")
        _doctor(candidate)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = config_path.with_name(config_path.name + "." + stamp + ".bak")
        shutil.copy2(config_path, backup)
        os.replace(candidate, config_path)
        return backup
    finally:
        candidate.unlink(missing_ok=True)


def save_routing(routing: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Path | None]:
    with SAVE_LOCK:
        validate_routing(routing, catalog)
        route_key = "autoRoutes" if routing.get("mode") == "auto" and "autoRoutes" in routing else "routes"
        aliases = [routing[route_key][tier][modality] for tier in routing_tiers(routing) for modality in MODALITIES]
        config_backup = ensure_pool_aliases(aliases, catalog)
        routing_backup = None
        if ROUTING_FILE.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            routing_backup = ROUTING_FILE.with_name(ROUTING_FILE.name + "." + stamp + ".bak")
            shutil.copy2(ROUTING_FILE, routing_backup)
        atomic_json(ROUTING_FILE, routing)
        return {"routing": routing_backup, "config": config_backup}


def write_runtime(port: int, token: str) -> None:
    atomic_json(RUNTIME_FILE, {
        "host": "127.0.0.1",
        "port": port,
        "token": token,
        "pid": os.getpid(),
    })


def clear_runtime(token: str) -> None:
    try:
        runtime = read_json(RUNTIME_FILE)
        if runtime.get("token") == token:
            RUNTIME_FILE.unlink()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
