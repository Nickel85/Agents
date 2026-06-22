"""Mongoose CLI for managing local agent capabilities."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import tempfile
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


AGENTS_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Agents"
APP_ROOT = AGENTS_ROOT / "mongoose"
CONFIG_PATH = APP_ROOT / "config.json"
USER_BIN = AGENTS_ROOT / "bin"
STATE_ROOT = AGENTS_ROOT / "state"
LOG_ROOT = AGENTS_ROOT / "logs"
JOBS_ROOT = STATE_ROOT / "jobs"
AGENT_STATE_ROOT = STATE_ROOT / "agents"
NON_SECRET_CONFIG_ROOT = STATE_ROOT / "config"
RUNTIME_ROOT = STATE_ROOT / "runtime"
STORAGE_ROOT = STATE_ROOT / "storage"
MEMORY_ROOT = STATE_ROOT / "memory"
LLM_PROFILE_ROOT = STATE_ROOT / "llm"
LLM_PROFILE_PATH = LLM_PROFILE_ROOT / "profiles.json"
DEFAULT_REGISTRY_URL = "https://github.com/Nickel85/Mongoose.git"
DEFAULT_LOG_RETENTION_DAYS = 30
DEFAULT_JOB_RETENTION = 50
DEFAULT_OLLAMA_TAGS_ENDPOINT = "http://localhost:11434/api/tags"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_LLM_PING_TIMEOUT_SECONDS = 10.0
DEFAULT_REMOTE_LLM_INVOKE_TIMEOUT_SECONDS = 30.0
DEFAULT_LOCAL_LLM_INVOKE_TIMEOUT_SECONDS = 300.0
DEFAULT_LOCAL_LLM_WARMUP_TIMEOUT_SECONDS = 300.0
OLLAMA_WINDOWS_INSTALL_URL = "https://ollama.com/install.ps1"
MONGOOSE_RELEASES_API_URL = "https://api.github.com/repos/Nickel85/Mongoose/releases"
MONGOOSE_RELEASE_ASSET_NAME = "mongoose.exe"
MONGOOSE_VERSION = "0.9.0"
MONGOOSE_RELEASE_KIND = "development"
MONGOOSE_RELEASE_TAG = ""
# Increment only for breaking manifest contract changes. Additive optional metadata stays on the same version.
SUPPORTED_MANIFEST_SCHEMA_VERSION = 1
SUPPORTED_RUNTIME_CONTRACT_VERSION = 1
COMMAND_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
PROVIDER_REQUIREMENT_KEYS = {
    "configuration",
    "logs",
    "state",
    "storage",
    "memory",
    "tools",
    "apiProfiles",
    "apis",
    "models",
    "llm",
    "execution",
}
AVAILABLE_RUNTIME_PROVIDERS = {"configuration", "logs", "state", "storage", "memory", "llm"}
REQUIREMENT_MODES = {"optional", "required"}
LLM_PROVIDERS = {"openai", "anthropic", "local-http", "fake"}
LLM_SECRET_MODES = {"env"}
SECRET_KEYWORDS = (
    "access_token",
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
)
SECRET_TEXT_PATTERN = re.compile(
    r"(?i)\b(access_token|api_key|authorization|password|secret|token)\s*[:=]\s*([^\s,;]+)"
)
POSTAL_ADDRESS_PATTERN = re.compile(
    r"(?i)\b\d{1,6}\s+[A-Za-z0-9 .'-]+\s+(street|st\.?|avenue|ave\.?|road|rd\.?|"
    r"drive|dr\.?|lane|ln\.?|boulevard|blvd\.?|court|ct\.?|place|pl\.?|way)\b"
)
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
MANIFEST_SECRET_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "client_secret",
    "password",
    "secret",
    "token",
}
ANSI_RESET = "\033[0m"
ANSI_STYLES = {
    "heading": "\033[36;1m",
    "success": "\033[32;1m",
    "warning": "\033[33;1m",
    "error": "\033[31;1m",
    "muted": "\033[2m",
    "selected": "\033[34;1m",
}
OUTPUT_COLOR_ENABLED = False


class ManifestValidationError(ValueError):
    def __init__(self, manifest_path: Path, errors: list[str]) -> None:
        self.manifest_path = manifest_path
        self.errors = errors
        super().__init__(self.format_message())

    def format_message(self) -> str:
        lines = [f"Invalid agent manifest: {self.manifest_path}"]
        lines.extend(f"- {error}" for error in self.errors)
        return "\n".join(lines)


class SelfUpdateError(RuntimeError):
    pass


def configure_output() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def color_requested_by_env() -> bool:
    value = os.environ.get("MONGOOSE_FORCE_COLOR", "")
    return value.strip().lower() in {"1", "true", "yes", "always"}


def color_disabled_by_env() -> bool:
    disabled_values = {
        os.environ.get("NO_COLOR", ""),
        os.environ.get("MONGOOSE_NO_COLOR", ""),
    }
    if any(value is not None and str(value).strip() for value in disabled_values):
        return True
    color_mode = os.environ.get("MONGOOSE_COLOR", "").strip().lower()
    return color_mode in {"0", "false", "never", "no"}


def should_use_color(no_color: bool = False) -> bool:
    if no_color or color_disabled_by_env():
        return False
    return color_requested_by_env() or sys.stdout.isatty()


def set_output_color(enabled: bool) -> None:
    global OUTPUT_COLOR_ENABLED
    OUTPUT_COLOR_ENABLED = enabled


def styled(text: str, style: str) -> str:
    if not OUTPUT_COLOR_ENABLED:
        return text
    prefix = ANSI_STYLES.get(style)
    if not prefix:
        return text
    return f"{prefix}{text}{ANSI_RESET}"


def print_heading(text: str) -> None:
    print(styled(text, "heading"))


def print_success(text: str) -> None:
    print(styled(text, "success"))


def print_warning(text: str) -> None:
    print(styled(text, "warning"))


def print_error(text: str, *, file: Any | None = None) -> None:
    print(styled(text, "error"), file=file or sys.stdout)


def print_muted(text: str) -> None:
    print(styled(text, "muted"))


def label_line(label: str, value: Any, style: str = "selected") -> str:
    return f"{styled(label + ':', style)} {value}"


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {
            "registryUrl": DEFAULT_REGISTRY_URL,
            "registryPath": str(APP_ROOT / "registry" / "Mongoose"),
        }

    return read_json(CONFIG_PATH)


def save_config(config: dict[str, Any]) -> None:
    write_json_atomic(CONFIG_PATH, config)


def state_contract() -> dict[str, str]:
    config = load_config()
    registry = registry_path(config)
    paths = {
        "version": MONGOOSE_VERSION,
        "releaseKind": MONGOOSE_RELEASE_KIND,
        "releaseTag": MONGOOSE_RELEASE_TAG,
        "cliSource": str(Path(__file__).resolve()),
        "root": str(AGENTS_ROOT),
        "bin": str(USER_BIN),
        "mongoose": str(APP_ROOT),
        "mongooseConfig": str(CONFIG_PATH),
        "registry": str(registry),
        "registryUrl": str(config.get("registryUrl", DEFAULT_REGISTRY_URL)),
        "registryRevision": registry_revision(registry),
        "registryStatus": registry_status(registry),
        "state": str(STATE_ROOT),
        "nonSecretConfig": str(NON_SECRET_CONFIG_ROOT),
        "agentState": str(AGENT_STATE_ROOT),
        "jobs": str(JOBS_ROOT),
        "logs": str(LOG_ROOT),
        "runtime": str(RUNTIME_ROOT),
        "storage": str(STORAGE_ROOT),
        "memory": str(MEMORY_ROOT),
        "llmProfiles": str(LLM_PROFILE_PATH),
    }
    return paths


def ensure_state_layout() -> dict[str, str]:
    paths = state_contract()
    directory_keys = {
        "root",
        "bin",
        "mongoose",
        "state",
        "nonSecretConfig",
        "agentState",
        "jobs",
        "logs",
        "runtime",
        "storage",
        "memory",
    }
    for key, value in paths.items():
        path = Path(value)
        if key in {"mongooseConfig", "llmProfiles"}:
            path.parent.mkdir(parents=True, exist_ok=True)
        elif key == "registry":
            path.parent.mkdir(parents=True, exist_ok=True)
        elif key in directory_keys:
            path.mkdir(parents=True, exist_ok=True)
    return paths


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(content, encoding=encoding)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not read JSON file: {path}") from exc


def write_json_atomic(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_llm_profiles() -> dict[str, Any]:
    data = read_json(LLM_PROFILE_PATH, default={"default": "", "profiles": {}})
    if not isinstance(data, dict):
        return {"default": "", "profiles": {}}
    profiles = data.get("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
    return {
        "default": str(data.get("default", "")).strip(),
        "profiles": profiles,
    }


def save_llm_profiles(data: dict[str, Any]) -> None:
    ensure_state_layout()
    write_json_atomic(LLM_PROFILE_PATH, data)


def normalize_profile_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("LLM profile name cannot be empty.")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", normalized):
        raise ValueError("LLM profile name must start with a letter and contain only letters, numbers, '.', '_' or '-'.")
    return normalized


def validate_llm_profile(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    provider = str(profile.get("provider", "")).strip()
    if provider not in LLM_PROVIDERS:
        errors.append(f"provider must be one of: {', '.join(sorted(LLM_PROVIDERS))}.")
    if not str(profile.get("model", "")).strip():
        errors.append("model is required.")
    secret = profile.get("secret", {})
    if secret and not isinstance(secret, dict):
        errors.append("secret must be an object.")
    elif isinstance(secret, dict):
        mode = str(secret.get("mode", "env")).strip()
        if mode not in LLM_SECRET_MODES:
            errors.append(f"secret.mode must be one of: {', '.join(sorted(LLM_SECRET_MODES))}.")
        env_name = str(secret.get("env", "")).strip()
        if provider in {"openai", "anthropic"} and not env_name:
            errors.append("secret.env is required for remote providers.")
        if env_name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name):
            errors.append("secret.env must be an environment variable name.")
    endpoint = str(profile.get("endpoint", "")).strip()
    if provider in {"local-http", "openai", "anthropic"} and endpoint:
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append("endpoint must be an http(s) URL when present.")
    if provider == "local-http" and not endpoint:
        errors.append("endpoint is required for local-http providers.")
    for key, value in profile.items():
        if manifest_secret_key(str(key)) and key != "secret" and str(value).strip():
            errors.append(f"profile.{key} must not contain a secret value.")
    if isinstance(secret, dict):
        for key, value in secret.items():
            if key not in {"mode", "env"} and str(value).strip():
                errors.append(f"profile.secret.{key} must not contain a secret value.")
    return errors


def llm_profile_summary(name: str, profile: dict[str, Any]) -> dict[str, Any]:
    secret = profile.get("secret", {}) if isinstance(profile.get("secret", {}), dict) else {}
    env_name = str(secret.get("env", "")).strip()
    return {
        "name": name,
        "provider": profile.get("provider", ""),
        "model": profile.get("model", ""),
        "endpoint": profile.get("endpoint", ""),
        "apiKeyEnv": env_name,
        "secretAvailable": bool(env_name and os.environ.get(env_name)),
        "capabilities": profile.get("capabilities", []),
    }


def llm_invoke_command(profile_name: str = "") -> list[str]:
    command = [sys.executable, str(Path(__file__).resolve()), "llm", "invoke", "--json"]
    if profile_name:
        command.extend(["--profile", profile_name])
    return command


def resolve_llm_profile(name: str | None = None) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    data = load_llm_profiles()
    profile_name = normalize_profile_name(name) if name else str(data.get("default", "")).strip()
    if not profile_name:
        return "", {}, runtime_error(
            "mongoose.llm_profile_missing",
            "No default LLM profile is configured. Run: mongoose llm add <name> ...",
        )
    profiles = data.get("profiles", {})
    profile = profiles.get(profile_name) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        return profile_name, {}, runtime_error(
            "mongoose.llm_profile_missing",
            f"LLM profile '{profile_name}' was not found.",
            profile=profile_name,
        )
    errors = validate_llm_profile(profile)
    if errors:
        return profile_name, profile, runtime_error(
            "mongoose.llm_profile_invalid",
            f"LLM profile '{profile_name}' is invalid.",
            profile=profile_name,
            errors=errors,
        )
    secret = profile.get("secret", {})
    env_name = str(secret.get("env", "")).strip() if isinstance(secret, dict) else ""
    if env_name and not os.environ.get(env_name):
        return profile_name, profile, runtime_error(
            "mongoose.llm_secret_missing",
            f"LLM profile '{profile_name}' is missing required environment variable {env_name}.",
            profile=profile_name,
            env=env_name,
        )
    return profile_name, profile, None


def is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(keyword in normalized for keyword in SECRET_KEYWORDS)


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if is_secret_key(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def redact_secret_text(message: str) -> str:
    return SECRET_TEXT_PATTERN.sub(lambda match: f"{match.group(1)}=[redacted]", message)


def redact_prompt_context_text(message: str) -> str:
    redacted = redact_secret_text(message)
    redacted = POSTAL_ADDRESS_PATTERN.sub("[redacted-address]", redacted)
    redacted = EMAIL_PATTERN.sub("[redacted-email]", redacted)
    return redacted


def redact_memory_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if is_secret_key(str(key)) else redact_memory_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_memory_value(item) for item in value]
    if isinstance(value, str):
        return redact_secret_text(value)
    return value


def redact_prompt_context_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if is_secret_key(str(key)) or "address" in str(key).lower() else redact_prompt_context_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_prompt_context_value(item) for item in value]
    if isinstance(value, str):
        return redact_prompt_context_text(value)
    return value


def append_log(component: str, message: str, level: str = "INFO", **metadata: Any) -> Path:
    ensure_state_layout()
    safe_component = re.sub(r"[^A-Za-z0-9_.-]+", "-", component).strip(".-") or "mongoose"
    log_path = LOG_ROOT / f"{safe_component}.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "component": safe_component,
        "message": redact_secret_text(message),
    }
    if metadata:
        record["metadata"] = redact_secrets(metadata)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, sort_keys=True) + "\n")
    return log_path


def cleanup_logs(retention_days: int = DEFAULT_LOG_RETENTION_DAYS) -> list[Path]:
    if retention_days < 0:
        raise ValueError("retention_days must be zero or greater")
    if not LOG_ROOT.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed: list[Path] = []
    for log_path in LOG_ROOT.glob("*.jsonl"):
        modified = datetime.fromtimestamp(log_path.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            log_path.unlink()
            removed.append(log_path)
    return removed


def registry_path(config: dict[str, Any]) -> Path:
    return Path(config["registryPath"]).expanduser().resolve()


def agent_manifest_paths(root: Path) -> list[Path]:
    agents_root = root / "agents"
    if not agents_root.exists():
        return []

    manifests: list[Path] = []
    for child in sorted(agents_root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue

        manifest = child / "agent.json"
        if manifest.exists():
            manifests.append(manifest)

    return manifests


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in list_value(value) if str(item).strip()]


def manifest_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in MANIFEST_SECRET_KEYS


def find_manifest_secret_values(value: Any, path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else str(key)
            if manifest_secret_key(str(key)) and str(item).strip():
                errors.append(f"{item_path} must not contain a secret value.")
            errors.extend(find_manifest_secret_values(item, item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(find_manifest_secret_values(item, f"{path}[{index}]"))
    elif isinstance(value, str) and SECRET_TEXT_PATTERN.search(value):
        errors.append(f"{path or 'manifest'} must not contain a secret-like value.")
    return errors


def validate_provider_requirements(value: Any, path: str) -> list[str]:
    errors: list[str] = []
    if value in ({}, None):
        return errors
    if not isinstance(value, dict):
        return [f"{path} must be an object when present."]

    for provider_name, requirement in value.items():
        provider = str(provider_name).strip()
        requirement_path = f"{path}.{provider}" if provider else path
        if provider not in PROVIDER_REQUIREMENT_KEYS:
            errors.append(
                f"{requirement_path} is not a supported provider requirement. "
                f"Use one of: {', '.join(sorted(PROVIDER_REQUIREMENT_KEYS))}."
            )
            continue

        if not isinstance(requirement, dict):
            errors.append(f"{requirement_path} must be an object.")
            continue

        mode = str(requirement.get("mode", "required")).strip()
        if mode not in REQUIREMENT_MODES:
            errors.append(f"{requirement_path}.mode must be one of: optional, required.")
        if mode == "required" and provider not in AVAILABLE_RUNTIME_PROVIDERS and provider != "execution":
            errors.append(
                f"{requirement_path} requires provider '{provider}', but Mongoose does not support that provider yet."
            )

        for list_field in ("names", "profiles", "features"):
            if requirement.get(list_field) is not None and not isinstance(requirement.get(list_field), list):
                errors.append(f"{requirement_path}.{list_field} must be a list when present.")
        if provider == "execution":
            platforms = requirement.get("platforms")
            if platforms is not None and not isinstance(platforms, list):
                errors.append(f"{requirement_path}.platforms must be a list when present.")
            python_version = requirement.get("python")
            if python_version is not None and not isinstance(python_version, str):
                errors.append(f"{requirement_path}.python must be a string when present.")

    return errors


def validate_manifest(manifest: dict[str, Any], manifest_path: Path) -> None:
    errors: list[str] = []

    required_string_fields = (
        "commandName",
        "displayName",
        "entrypointPath",
        "example",
        "description",
    )
    for field_name in required_string_fields:
        if not str(manifest.get(field_name, "")).strip():
            errors.append(f"Missing required string field: {field_name}")

    command_name = str(manifest.get("commandName", "")).strip()
    if command_name and not COMMAND_NAME_PATTERN.match(command_name):
        errors.append("commandName must start with a letter and contain only letters, numbers, '_' or '-'.")

    schema_version = manifest.get("schemaVersion", SUPPORTED_MANIFEST_SCHEMA_VERSION)
    if not isinstance(schema_version, int):
        errors.append("schemaVersion must be an integer when present.")
    elif schema_version > SUPPORTED_MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"schemaVersion {schema_version} is newer than supported version {SUPPORTED_MANIFEST_SCHEMA_VERSION}."
        )

    agent_dir = manifest_path.parent
    entrypoint_path = str(manifest.get("entrypointPath", "")).strip()
    if entrypoint_path:
        if Path(entrypoint_path).is_absolute():
            errors.append("entrypointPath must be relative to the agent directory.")
        elif not (agent_dir / entrypoint_path).exists():
            errors.append(f"entrypointPath does not exist: {entrypoint_path}")

    identity = manifest.get("identity", {})
    if identity and not isinstance(identity, dict):
        errors.append("identity must be an object when present.")

    errors.extend(validate_provider_requirements(manifest.get("requires", {}), "requires"))

    entrypoints = manifest.get("entrypoints", {})
    if entrypoints and not isinstance(entrypoints, dict):
        errors.append("entrypoints must be an object when present.")
    elif isinstance(entrypoints, dict):
        for name, relative_path in entrypoints.items():
            relative = str(relative_path).strip()
            if not relative:
                errors.append(f"entrypoints.{name} must be a non-empty path.")
            elif Path(relative).is_absolute():
                errors.append(f"entrypoints.{name} must be relative to the agent directory.")
            elif not (agent_dir / relative).exists():
                errors.append(f"entrypoints.{name} does not exist: {relative}")

    capabilities = manifest.get("capabilities", [])
    if capabilities and not isinstance(capabilities, list):
        errors.append("capabilities must be a list when present.")
    elif isinstance(capabilities, list):
        capability_names: set[str] = set()
        for index, capability in enumerate(capabilities):
            prefix = f"capabilities[{index}]"
            if not isinstance(capability, dict):
                errors.append(f"{prefix} must be an object.")
                continue

            name = str(capability.get("name", "")).strip()
            if not name:
                errors.append(f"{prefix}.name is required.")
            elif name in capability_names:
                errors.append(f"{prefix}.name duplicates capability '{name}'.")
            else:
                capability_names.add(name)

            if not str(capability.get("description", "")).strip():
                errors.append(f"{prefix}.description is required.")

            if capability.get("taskTypes") is not None and not isinstance(capability.get("taskTypes"), list):
                errors.append(f"{prefix}.taskTypes must be a list.")

            if capability.get("requiredInputs") is not None and not isinstance(capability.get("requiredInputs"), list):
                errors.append(f"{prefix}.requiredInputs must be a list.")

            config = capability.get("configuration", capability.get("config", {}))
            if config and not isinstance(config, dict):
                errors.append(f"{prefix}.configuration must be an object.")

            errors.extend(validate_provider_requirements(capability.get("requires", {}), f"{prefix}.requires"))

            llm = capability.get("llm", {})
            if llm and not isinstance(llm, dict):
                errors.append(f"{prefix}.llm must be an object.")
            elif isinstance(llm, dict):
                mode = str(llm.get("mode", "none")).strip()
                if mode and mode not in {"none", "optional", "required"}:
                    errors.append(f"{prefix}.llm.mode must be one of: none, optional, required.")
                if mode == "required" and not llm.get("deterministicFallback"):
                    errors.append(f"{prefix}.llm.deterministicFallback must explain behavior for required LLM use.")

            entrypoint = str(capability.get("entrypointPath", "")).strip()
            if entrypoint:
                if Path(entrypoint).is_absolute():
                    errors.append(f"{prefix}.entrypointPath must be relative to the agent directory.")
                elif not (agent_dir / entrypoint).exists():
                    errors.append(f"{prefix}.entrypointPath does not exist: {entrypoint}")

    compatibility = manifest.get("compatibility", {})
    if compatibility and not isinstance(compatibility, dict):
        errors.append("compatibility must be an object when present.")

    errors.extend(find_manifest_secret_values(manifest))

    if errors:
        raise ManifestValidationError(manifest_path, errors)


def load_agent_registry(root: Path) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}

    for manifest_path in agent_manifest_paths(root):
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict):
            raise ManifestValidationError(manifest_path, ["Manifest must be a JSON object."])
        validate_manifest(manifest, manifest_path)

        command_name = str(manifest.get("commandName", "")).strip()
        registry[command_name] = agent_record(manifest, manifest_path)

    return registry


def discover_capabilities(agent_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    manifest_capabilities = manifest.get("capabilities")
    if isinstance(manifest_capabilities, list):
        capabilities = []
        for capability in manifest_capabilities:
            if not isinstance(capability, dict):
                continue
            name = str(capability.get("name", "")).strip()
            if not name:
                continue
            capabilities.append(
                {
                    "name": name,
                    "displayName": str(capability.get("displayName", name)).strip(),
                    "description": str(capability.get("description", "")).strip(),
                    "taskTypes": string_list(capability.get("taskTypes", [])),
                    "requiredInputs": capability.get("requiredInputs", []),
                    "requires": capability.get("requires", {}),
                    "configuration": capability.get("configuration", capability.get("config", {})),
                    "compatibility": capability.get("compatibility", {}),
                    "llm": capability.get("llm", {"mode": "none"}),
                    "deterministicFallback": str(capability.get("deterministicFallback", "")).strip(),
                    "entrypointPath": str(capability.get("entrypointPath", "")).strip(),
                }
            )
        return capabilities

    capabilities_root = agent_dir / "capabilities"
    if not capabilities_root.exists():
        return []

    capabilities = []
    for child in sorted(capabilities_root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        readme = child / "README.md"
        capabilities.append(
            {
                "name": child.name,
                "displayName": child.name,
                "description": first_markdown_paragraph(readme),
                "taskTypes": [],
                "requiredInputs": [],
                "requires": {},
                "configuration": {},
                "compatibility": {},
                "llm": {"mode": "none"},
                "deterministicFallback": "",
                "entrypointPath": "",
            }
        )
    return capabilities


def first_markdown_paragraph(path: Path) -> str:
    if not path.exists():
        return ""

    for line in path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            return cleaned
    return ""


def agent_record(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    command_name = str(manifest.get("commandName", "")).strip()
    entrypoint_path = str(manifest.get("entrypointPath", "")).strip()
    agent_dir = manifest_path.parent.resolve()
    entrypoint = (agent_dir / entrypoint_path).resolve()
    return {
        "schemaVersion": manifest.get("schemaVersion", SUPPORTED_MANIFEST_SCHEMA_VERSION),
        "id": manifest.get("id", command_name),
        "commandName": command_name,
        "displayName": manifest.get("displayName", command_name),
        "description": manifest.get("description", ""),
        "example": manifest.get("example", "Hello"),
        "version": manifest.get("version", ""),
        "identity": manifest.get("identity", {}),
        "manifest": manifest,
        "entrypoint": str(entrypoint),
        "entrypointPath": entrypoint_path,
        "entrypoints": manifest.get("entrypoints", {}),
        "sourcePath": str(agent_dir),
        "manifestPath": str(manifest_path.resolve()),
        "taskTypes": string_list(manifest.get("taskTypes", [])),
        "requiredInputs": manifest.get("requiredInputs", []),
        "requires": manifest.get("requires", {}),
        "configuration": manifest.get("configuration", {}),
        "compatibility": manifest.get("compatibility", {}),
        "llm": manifest.get("llm", {"mode": "none"}),
        "capabilities": discover_capabilities(agent_dir, manifest),
    }


def load_agent_from_source(source: str) -> dict[str, Any] | None:
    source_path = Path(source).expanduser()
    if not source_path.exists():
        return None

    manifest_path = source_path if source_path.is_file() else source_path / "agent.json"
    if not manifest_path.exists():
        raise ValueError(f"No agent.json manifest found at {source_path}")

    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"Agent manifest must be a JSON object: {manifest_path}")
    validate_manifest(manifest, manifest_path)

    return agent_record(manifest, manifest_path)


def installed_agent_path(command_name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", command_name).strip(".-")
    if not safe_name:
        raise ValueError("Agent name cannot be empty.")
    return AGENT_STATE_ROOT / f"{safe_name}.json"


def save_installed_agent(agent: dict[str, Any], launcher_path: Path) -> None:
    ensure_state_layout()
    installed = {
        "commandName": agent["commandName"],
        "schemaVersion": agent.get("schemaVersion", SUPPORTED_MANIFEST_SCHEMA_VERSION),
        "id": agent.get("id", agent["commandName"]),
        "displayName": agent.get("displayName", agent["commandName"]),
        "description": agent.get("description", ""),
        "version": agent.get("version", ""),
        "identity": agent.get("identity", {}),
        "example": agent.get("example", "Hello"),
        "sourcePath": agent.get("sourcePath", ""),
        "manifestPath": agent.get("manifestPath", ""),
        "entrypoint": agent.get("entrypoint", ""),
        "entrypointPath": agent.get("entrypointPath", ""),
        "entrypoints": agent.get("entrypoints", {}),
        "launcherPath": str(launcher_path),
        "installedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "taskTypes": agent.get("taskTypes", []),
        "requiredInputs": agent.get("requiredInputs", []),
        "requires": agent.get("requires", {}),
        "configuration": agent.get("configuration", {}),
        "compatibility": agent.get("compatibility", {}),
        "llm": agent.get("llm", {"mode": "none"}),
        "manifest": agent.get("manifest", {}),
        "capabilities": agent.get("capabilities", []),
    }
    write_json_atomic(installed_agent_path(agent["commandName"]), installed)


def load_installed_agents() -> dict[str, dict[str, Any]]:
    if not AGENT_STATE_ROOT.exists():
        return {}

    installed: dict[str, dict[str, Any]] = {}
    for path in sorted(AGENT_STATE_ROOT.glob("*.json")):
        record = read_json(path, default={})
        if not isinstance(record, dict):
            continue
        command_name = str(record.get("commandName", "")).strip()
        if command_name:
            installed[command_name] = record
    return installed


def load_installed_agent(command_name: str) -> dict[str, Any] | None:
    record = read_json(installed_agent_path(command_name), default=None)
    return record if isinstance(record, dict) else None


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = value.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(value)
    return unique


def required_configuration_names(agent: dict[str, Any], capability: dict[str, Any]) -> list[str]:
    names: list[str] = []
    capability_configuration = capability.get("configuration", {})
    capability_declares_requirements = (
        "requiredInputs" in capability
        or (
            isinstance(capability_configuration, dict)
            and "required" in capability_configuration
        )
    )

    if not capability_declares_requirements:
        names.extend(string_list(agent.get("requiredInputs", [])))
        agent_configuration = agent.get("configuration", {})
        if isinstance(agent_configuration, dict):
            names.extend(string_list(agent_configuration.get("required", [])))

    names.extend(string_list(capability.get("requiredInputs", [])))
    if isinstance(capability_configuration, dict):
        names.extend(string_list(capability_configuration.get("required", [])))

    return unique_strings(names)


def missing_required_configuration(agent: dict[str, Any], capability: dict[str, Any]) -> list[str]:
    return [name for name in required_configuration_names(agent, capability) if not os.environ.get(name)]


def runtime_contract_requirement(agent: dict[str, Any], capability: dict[str, Any] | None = None) -> int:
    for source in (capability or {}, agent):
        compatibility = source.get("compatibility", {})
        if not isinstance(compatibility, dict):
            continue
        value = compatibility.get("mongooseRuntimeContract", compatibility.get("runtimeContract"))
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return SUPPORTED_RUNTIME_CONTRACT_VERSION


def runtime_error(code: str, message: str, **details: Any) -> dict[str, Any]:
    error: dict[str, Any] = {
        "contractVersion": SUPPORTED_RUNTIME_CONTRACT_VERSION,
        "code": code,
        "message": message,
    }
    if details:
        error["details"] = redact_secrets(details)
    return error


def print_runtime_error(error: dict[str, Any]) -> None:
    print_error(str(error.get("message", "Runtime error.")))
    print(label_line("Runtime error", error.get("code", "mongoose.runtime_error"), "error"))
    details = error.get("details")
    if isinstance(details, dict) and details:
        print(label_line("Details", json.dumps(details, sort_keys=True), "muted"))


def runtime_config_status(agent: dict[str, Any], capability: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    capability = capability or {}
    names = required_configuration_names(agent, capability)
    optional_names: list[str] = []
    for source in (agent.get("configuration", {}), capability.get("configuration", {})):
        if isinstance(source, dict):
            optional_names.extend(string_list(source.get("optional", [])))

    records = []
    for name in unique_strings(names + optional_names):
        records.append(
            {
                "name": name,
                "required": name in names,
                "available": bool(os.environ.get(name)),
                "source": "environment",
                "secret": is_secret_key(name),
            }
        )
    return records


def memory_records_path() -> Path:
    return MEMORY_ROOT / "records.jsonl"


def memory_record_id() -> str:
    return f"memory_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{os.getpid()}"


def normalize_memory_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized["schemaVersion"] = normalized.get("schemaVersion", 1)
    normalized["recordType"] = str(normalized.get("recordType", "memory_record")).strip() or "memory_record"
    normalized["recordId"] = str(normalized.get("recordId", "")).strip() or memory_record_id()
    normalized["createdAt"] = str(normalized.get("createdAt", "")).strip() or now_utc_iso()
    redaction = normalized.get("redaction", {})
    if not isinstance(redaction, dict):
        redaction = {}
    redaction.setdefault("secretsRemoved", True)
    normalized["redaction"] = redaction
    redacted = redact_memory_value(normalized)
    if isinstance(redacted, dict):
        redacted["redaction"] = redaction
    return redacted


def append_memory_record(record: dict[str, Any]) -> dict[str, Any]:
    ensure_state_layout()
    normalized = normalize_memory_record(record)
    path = memory_records_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(normalized, sort_keys=True) + "\n")
    return normalized


def load_memory_records() -> list[dict[str, Any]]:
    path = memory_records_path()
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return list(reversed(records))


def parse_memory_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def nested_dict_value(record: dict[str, Any], *path: str) -> Any:
    value: Any = record
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key, "")
    return value


def memory_confidence_values(record: dict[str, Any]) -> list[float]:
    values: list[float] = []
    candidates = [
        record.get("confidence", ""),
        nested_dict_value(record, "decision", "confidence"),
        nested_dict_value(record, "recommendation", "confidence"),
        nested_dict_value(record, "outcome", "confidence"),
    ]
    for candidate in candidates:
        try:
            values.append(float(candidate))
        except (TypeError, ValueError):
            continue
    return values


def memory_status_values(record: dict[str, Any]) -> set[str]:
    values = [
        record.get("status", ""),
        nested_dict_value(record, "loop", "status"),
        nested_dict_value(record, "outcome", "status"),
        nested_dict_value(record, "userDecision", "status"),
        nested_dict_value(record, "decision", "status"),
    ]
    return {str(value).lower() for value in values if value}


def memory_outcome_values(record: dict[str, Any]) -> set[str]:
    values = [
        record.get("outcome", ""),
        nested_dict_value(record, "outcome", "status"),
        nested_dict_value(record, "outcome", "summary"),
        nested_dict_value(record, "outcome", "result"),
    ]
    return {str(value).lower() for value in values if value}


def memory_record_matches(record: dict[str, Any], args: argparse.Namespace) -> bool:
    filters = {
        "record_type": ("recordType", getattr(args, "record_type", "")),
        "agent": ("agentId", getattr(args, "agent", "")),
        "capability": ("capabilityId", getattr(args, "capability", "")),
    }
    for _name, (field, expected) in filters.items():
        if expected and str(record.get(field, "")).lower() != str(expected).lower():
            return False
    expected_status = str(getattr(args, "status", "") or "").strip().lower()
    if expected_status and expected_status not in memory_status_values(record):
        return False
    expected_outcome = str(getattr(args, "outcome", "") or "").strip().lower()
    if expected_outcome:
        if not any(expected_outcome in value for value in memory_outcome_values(record)):
            return False
    from_time = parse_memory_time(str(getattr(args, "from_date", "") or ""))
    to_time = parse_memory_time(str(getattr(args, "to_date", "") or ""))
    record_time = parse_memory_time(str(record.get("createdAt", "") or ""))
    if from_time and (record_time is None or record_time < from_time):
        return False
    if to_time and (record_time is None or record_time > to_time):
        return False
    min_confidence = getattr(args, "min_confidence", None)
    if min_confidence is not None:
        confidence_values = memory_confidence_values(record)
        if not confidence_values or max(confidence_values) < float(min_confidence):
            return False
    subject = str(getattr(args, "subject", "") or "").strip().lower()
    if subject:
        haystack = json.dumps(record, sort_keys=True).lower()
        if subject not in haystack:
            return False
    return True


def query_memory_records(args: argparse.Namespace) -> list[dict[str, Any]]:
    limit = max(0, int(getattr(args, "limit", 20)))
    records = [record for record in load_memory_records() if memory_record_matches(record, args)]
    return records[:limit] if limit else records


def first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            text = first_text(value.get("summary"), value.get("message"), value.get("description"), value.get("request"))
            if text:
                return text
    return ""


def memory_record_prompt_summary(record: dict[str, Any]) -> str:
    summary = first_text(
        nested_dict_value(record, "decision", "summary"),
        nested_dict_value(record, "recommendation", "summary"),
        nested_dict_value(record, "outcome", "summary"),
        nested_dict_value(record, "goal", "request"),
        nested_dict_value(record, "goal", "summary"),
        record.get("summary", ""),
    )
    if not summary:
        events = record.get("events", [])
        if isinstance(events, list):
            event_messages = [
                str(event.get("message", "")).strip()
                for event in events
                if isinstance(event, dict) and str(event.get("message", "")).strip()
            ]
            summary = "; ".join(event_messages[:3])
    return redact_prompt_context_text(summary or "Relevant memory record.")


def prompt_context_record(record: dict[str, Any]) -> dict[str, Any]:
    user_decision = record.get("userDecision", {})
    if not isinstance(user_decision, dict):
        user_decision = {"status": str(user_decision)}
    outcome = record.get("outcome", {})
    if not isinstance(outcome, dict):
        outcome = {"summary": str(outcome)}
    context = {
        "recordId": record.get("recordId", ""),
        "recordType": record.get("recordType", ""),
        "agentId": record.get("agentId", ""),
        "capabilityId": record.get("capabilityId", ""),
        "createdAt": record.get("createdAt", ""),
        "summary": memory_record_prompt_summary(record),
        "confidence": max(memory_confidence_values(record), default=None),
        "userDecision": {
            "status": user_decision.get("status", ""),
            "summary": user_decision.get("summary", ""),
        },
        "outcome": {
            "status": outcome.get("status", ""),
            "summary": outcome.get("summary", ""),
        },
        "source": {
            "provider": "mongoose.memory.v1",
            "recordId": record.get("recordId", ""),
        },
    }
    return redact_prompt_context_value(context)


def memory_prompt_context(args: argparse.Namespace) -> dict[str, Any]:
    records = query_memory_records(args)
    context_records = [prompt_context_record(record) for record in records]
    return {
        "interface": "mongoose.prompt-context.v1",
        "generatedAt": now_utc_iso(),
        "query": {
            "agentId": getattr(args, "agent", "") or "",
            "capabilityId": getattr(args, "capability", "") or "",
            "subject": getattr(args, "subject", "") or "",
            "recordType": getattr(args, "record_type", "") or "",
            "status": getattr(args, "status", "") or "",
            "outcome": getattr(args, "outcome", "") or "",
            "from": getattr(args, "from_date", "") or "",
            "to": getattr(args, "to_date", "") or "",
            "minConfidence": getattr(args, "min_confidence", None),
            "limit": max(0, int(getattr(args, "limit", 8))),
        },
        "records": context_records,
        "fallback": {
            "used": not context_records,
            "message": "No relevant memory records were found. Continue without memory-backed context.",
        },
        "guardrails": {
            "authority": "informational-only",
            "canApproveActions": False,
            "canMutateState": False,
            "redaction": "secrets, addresses, and unnecessary PII are removed before prompt use",
        },
    }


def runtime_provider_descriptors(agent: dict[str, Any], capability: dict[str, Any] | None = None) -> dict[str, Any]:
    command_name = str(agent.get("commandName", "agent")).strip() or "agent"
    capability_name = str((capability or {}).get("name", "")).strip()
    storage_scope = re.sub(r"[^A-Za-z0-9_.-]+", "-", command_name).strip(".-") or "agent"
    storage_path = STORAGE_ROOT / storage_scope
    if capability_name:
        storage_path = storage_path / re.sub(r"[^A-Za-z0-9_.-]+", "-", capability_name).strip(".-")
    storage_path.mkdir(parents=True, exist_ok=True)

    llm = (capability or {}).get("llm", agent.get("llm", {"mode": "none"}))
    llm_mode = llm.get("mode", "none") if isinstance(llm, dict) else "none"
    llm_profiles = load_llm_profiles()
    default_llm = str(llm_profiles.get("default", "")).strip()
    default_profile = llm_profiles.get("profiles", {}).get(default_llm, {}) if default_llm else {}
    default_summary = (
        llm_profile_summary(default_llm, default_profile)
        if default_llm and isinstance(default_profile, dict)
        else {}
    )
    _, _, default_error = resolve_llm_profile(default_llm) if default_llm else ("", {}, None)
    return {
        "configuration": {
            "available": True,
            "interface": "mongoose.configuration.v1",
            "values": runtime_config_status(agent, capability),
            "secrets": "referenced-by-name",
        },
        "logs": {
            "available": True,
            "interface": "mongoose.logs.v1",
            "path": str(LOG_ROOT),
        },
        "state": {
            "available": True,
            "interface": "mongoose.state.v1",
            "path": str(STATE_ROOT),
        },
        "storage": {
            "available": True,
            "interface": "mongoose.storage.local.v1",
            "path": str(storage_path),
        },
        "memory": {
            "available": True,
            "interface": "mongoose.memory.v1",
            "path": str(MEMORY_ROOT),
            "recordsPath": str(memory_records_path()),
            "appendCommand": [sys.executable, str(Path(__file__).resolve()), "memory", "append", "--json"],
            "listCommand": [sys.executable, str(Path(__file__).resolve()), "memory", "list", "--json"],
            "contextCommand": [sys.executable, str(Path(__file__).resolve()), "memory", "context", "--json"],
            "reason": "",
        },
        "tools": {
            "available": False,
            "interface": "mongoose.tools.v1",
            "reason": "No tool provider is configured yet.",
        },
        "apiProfiles": {
            "available": False,
            "interface": "mongoose.api-profiles.v1",
            "reason": "No API profile provider is configured yet.",
        },
        "llm": {
            "available": bool(default_summary and default_error is None),
            "interface": "mongoose.llm.v1",
            "mode": llm_mode,
            "defaultProfile": default_llm,
            "profile": default_summary,
            "invokeCommand": llm_invoke_command(default_llm),
            "input": "stdin prompt text",
            "output": "json",
            "reason": "" if default_summary else "No default LLM profile is configured yet.",
        },
    }


def runtime_context(
    *,
    mode: str,
    agent: dict[str, Any],
    agent_args: list[str],
    capability: dict[str, Any] | None = None,
    route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = ensure_state_layout()
    return {
        "contractVersion": SUPPORTED_RUNTIME_CONTRACT_VERSION,
        "invocation": {
            "id": f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{os.getpid()}",
            "mode": mode,
            "arguments": agent_args,
            "createdAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        },
        "mongoose": {
            "version": MONGOOSE_VERSION,
            "releaseKind": MONGOOSE_RELEASE_KIND,
            "releaseTag": MONGOOSE_RELEASE_TAG,
            "runtimeContractVersion": SUPPORTED_RUNTIME_CONTRACT_VERSION,
        },
        "agent": {
            "commandName": agent.get("commandName", ""),
            "displayName": agent.get("displayName", ""),
            "version": agent.get("version", ""),
            "sourcePath": agent.get("sourcePath", ""),
            "manifestPath": agent.get("manifestPath", ""),
            "schemaVersion": agent.get("schemaVersion", SUPPORTED_MANIFEST_SCHEMA_VERSION),
        },
        "capability": capability or None,
        "route": route or None,
        "paths": paths,
        "providers": runtime_provider_descriptors(agent, capability),
        "errors": {
            "interface": "mongoose.runtime-errors.v1",
            "fields": ["contractVersion", "code", "message", "details"],
        },
    }


def write_runtime_context(context: dict[str, Any]) -> Path:
    ensure_state_layout()
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    invocation = context.get("invocation", {})
    invocation_id = str(invocation.get("id", f"{os.getpid()}")).strip()
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", invocation_id).strip(".-") or str(os.getpid())
    path = RUNTIME_ROOT / f"{safe_id}.json"
    write_json_atomic(path, context)
    return path


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_state_name(value: str, fallback: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return safe_name or fallback


def job_path(job_id: str) -> Path:
    return JOBS_ROOT / f"{safe_state_name(job_id, 'job')}.json"


def job_log_path(job_id: str) -> Path:
    return LOG_ROOT / f"job-{safe_state_name(job_id, 'job')}.jsonl"


def output_summary(stdout: str, stderr: str, max_chars: int = 2000) -> dict[str, Any]:
    redacted_stdout = redact_secret_text(stdout or "")
    redacted_stderr = redact_secret_text(stderr or "")
    combined = "\n".join(part for part in (redacted_stdout.strip(), redacted_stderr.strip()) if part)
    if len(combined) > max_chars:
        combined = f"{combined[:max_chars]}..."
    return {
        "stdoutPreview": redacted_stdout[:max_chars],
        "stderrPreview": redacted_stderr[:max_chars],
        "combinedPreview": combined,
        "truncated": len(redacted_stdout) > max_chars or len(redacted_stderr) > max_chars,
    }


def write_job_record(job: dict[str, Any]) -> Path:
    ensure_state_layout()
    path = job_path(str(job.get("id", "")))
    write_json_atomic(path, redact_secrets(job))
    return path


def append_job_log(job_id: str, message: str, level: str = "INFO", **metadata: Any) -> Path:
    ensure_state_layout()
    path = job_log_path(job_id)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "component": "mongoose.job",
        "jobId": job_id,
        "message": redact_secret_text(message),
    }
    if metadata:
        record["metadata"] = redact_secrets(metadata)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def begin_job(
    *,
    context: dict[str, Any],
    mode: str,
    agent: dict[str, Any],
    entrypoint: Path,
    agent_args: list[str],
    capability: dict[str, Any] | None = None,
    route: dict[str, Any] | None = None,
    context_path: Path,
) -> dict[str, Any]:
    invocation = context.get("invocation", {})
    job_id = str(invocation.get("id", f"{int(time.time())}-{os.getpid()}"))
    started_at = now_utc_iso()
    job = {
        "schemaVersion": 1,
        "id": job_id,
        "status": "running",
        "mode": mode,
        "agent": {
            "commandName": agent.get("commandName", ""),
            "displayName": agent.get("displayName", ""),
            "version": agent.get("version", ""),
        },
        "capability": capability.get("name", "") if isinstance(capability, dict) else "",
        "route": route or {},
        "arguments": redact_secrets(agent_args),
        "entrypoint": str(entrypoint),
        "startedAt": started_at,
        "finishedAt": "",
        "durationMs": 0,
        "exitCode": None,
        "contextPath": str(context_path),
        "logPath": str(job_log_path(job_id)),
        "outputSummary": {},
    }
    write_job_record(job)
    append_job_log(job_id, "Job started.", mode=mode, agent=job["agent"], capability=job["capability"])
    return job


def finish_job(job: dict[str, Any], exit_code: int, stdout: str, stderr: str) -> dict[str, Any]:
    finished_at = datetime.now(timezone.utc)
    started = datetime.fromisoformat(str(job.get("startedAt", now_utc_iso())))
    status = "succeeded" if exit_code == 0 else "failed"
    job.update(
        {
            "status": status,
            "finishedAt": finished_at.replace(microsecond=0).isoformat(),
            "durationMs": int((finished_at - started).total_seconds() * 1000),
            "exitCode": exit_code,
            "outputSummary": output_summary(stdout, stderr),
        }
    )
    write_job_record(job)
    append_job_log(job["id"], f"Job {status}.", level="INFO" if exit_code == 0 else "ERROR", exitCode=exit_code)
    prune_jobs(DEFAULT_JOB_RETENTION)
    return job


def load_job_records() -> list[dict[str, Any]]:
    if not JOBS_ROOT.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(JOBS_ROOT.glob("*.json")):
        record = read_json(path, default={})
        if isinstance(record, dict) and record.get("id"):
            records.append(record)
    return sorted(records, key=lambda item: str(item.get("startedAt", "")), reverse=True)


def load_job_record(job_id: str) -> dict[str, Any] | None:
    path = job_path(job_id)
    record = read_json(path, default=None)
    return record if isinstance(record, dict) else None


def prune_jobs(max_records: int) -> list[Path]:
    if max_records <= 0 or not JOBS_ROOT.exists():
        return []
    records = load_job_records()
    stale = records[max_records:]
    removed: list[Path] = []
    for record in stale:
        path = job_path(str(record.get("id", "")))
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def runtime_state_path() -> Path:
    return RUNTIME_ROOT / "runtime.json"


def load_runtime_state() -> dict[str, Any]:
    state = read_json(runtime_state_path(), default={})
    if not isinstance(state, dict):
        state = {}
    return {
        "schemaVersion": 1,
        "status": state.get("status", "stopped"),
        "startedAt": state.get("startedAt", ""),
        "updatedAt": state.get("updatedAt", ""),
        "message": state.get("message", "No background runtime daemon is running."),
    }


def save_runtime_state(status: str, message: str) -> dict[str, Any]:
    ensure_state_layout()
    existing = load_runtime_state()
    timestamp = now_utc_iso()
    state = {
        "schemaVersion": 1,
        "status": status,
        "startedAt": timestamp if status == "running" else existing.get("startedAt", ""),
        "updatedAt": timestamp,
        "message": message,
    }
    write_json_atomic(runtime_state_path(), state)
    return state


def run_agent_with_runtime(
    *,
    mode: str,
    agent: dict[str, Any],
    entrypoint: Path,
    agent_args: list[str],
    capability: dict[str, Any] | None = None,
    route: dict[str, Any] | None = None,
) -> int:
    context = runtime_context(
        mode=mode,
        agent=agent,
        capability=capability,
        route=route,
        agent_args=agent_args,
    )
    context_path = write_runtime_context(context)
    job = begin_job(
        context=context,
        mode=mode,
        agent=agent,
        capability=capability,
        route=route,
        entrypoint=entrypoint,
        agent_args=agent_args,
        context_path=context_path,
    )
    env = {
        **os.environ,
        "MONGOOSE_RUNTIME_CONTEXT": str(context_path),
        "MONGOOSE_RUNTIME_CONTRACT_VERSION": str(SUPPORTED_RUNTIME_CONTRACT_VERSION),
        "MONGOOSE_JOB_ID": job["id"],
    }
    completed = subprocess.run(
        [sys.executable, str(entrypoint), *agent_args],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    finish_job(job, completed.returncode, completed.stdout or "", completed.stderr or "")
    return completed.returncode


def capability_entrypoint(agent: dict[str, Any], capability: dict[str, Any]) -> Path:
    entrypoint_path = str(capability.get("entrypointPath", "")).strip()
    if not entrypoint_path:
        return Path(str(agent.get("entrypoint", "")))
    return (Path(str(agent.get("sourcePath", ""))) / entrypoint_path).resolve()


def installed_capability_records(installed: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    agents = installed if installed is not None else load_installed_agents()
    records: list[dict[str, Any]] = []
    for command_name, agent in sorted(agents.items()):
        for capability in list_value(agent.get("capabilities", [])):
            if not isinstance(capability, dict):
                continue
            capability_name = str(capability.get("name", "")).strip()
            if not capability_name:
                continue
            task_types = unique_strings(
                string_list(capability.get("taskTypes", [])) + string_list(agent.get("taskTypes", []))
            )
            records.append(
                {
                    "agent": agent,
                    "agentName": command_name,
                    "capability": capability,
                    "capabilityName": capability_name,
                    "displayName": str(capability.get("displayName", capability_name)).strip(),
                    "description": str(capability.get("description", "")).strip(),
                    "taskTypes": task_types,
                    "entrypoint": capability_entrypoint(agent, capability),
                }
            )
    return records


def route_search_text(record: dict[str, Any]) -> str:
    values = [
        record["agentName"],
        record["capabilityName"],
        record.get("displayName", ""),
        record.get("description", ""),
        *record.get("taskTypes", []),
    ]
    return " ".join(str(value).lower() for value in values if value)


def route_score(record: dict[str, Any], query: str) -> int:
    normalized_query = query.lower()
    if not normalized_query.strip():
        return 0

    text = route_search_text(record)
    score = 0
    for task_type in record.get("taskTypes", []):
        normalized_task_type = task_type.lower()
        if normalized_task_type and normalized_task_type in normalized_query:
            score += 5
    for token in re.findall(r"[a-z0-9][a-z0-9_-]*", normalized_query):
        if token and token in text:
            score += 1
    return score


def parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def format_route_candidate(record: dict[str, Any]) -> str:
    task_types = record.get("taskTypes", [])
    suffix = f" [{', '.join(task_types)}]" if task_types else ""
    return f"{record['agentName']}::{record['capabilityName']}{suffix}"


def route_candidate_pool(args: argparse.Namespace, capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if args.agent:
        capabilities = [
            record for record in capabilities if record["agentName"].lower() == args.agent.lower()
        ]
    if args.capability:
        capabilities = [
            record
            for record in capabilities
            if record["capabilityName"].lower() == args.capability.lower()
        ]
    return capabilities


def deterministic_route_candidates(
    args: argparse.Namespace,
    capabilities: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    query = " ".join(args.request or []).strip()
    if args.task_type:
        requested = args.task_type.lower()
        direct_matches = [
            record
            for record in capabilities
            if requested in {task_type.lower() for task_type in record.get("taskTypes", [])}
        ]
        if not query or len(direct_matches) <= 1:
            return direct_matches, query
        capabilities = direct_matches

    scored = [(route_score(record, query), record) for record in capabilities]
    scored = [(score, record) for score, record in scored if score > 0]
    if not scored:
        return [], query

    best_score = max(score for score, _record in scored)
    return [record for score, record in scored if score == best_score], query


def route_candidates_for_llm(args: argparse.Namespace, capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if args.task_type:
        requested = args.task_type.lower()
        direct_matches = [
            record
            for record in capabilities
            if requested in {task_type.lower() for task_type in record.get("taskTypes", [])}
        ]
        return direct_matches
    return capabilities


def matching_route_candidates(args: argparse.Namespace) -> tuple[list[dict[str, Any]], str]:
    return deterministic_route_candidates(args, route_candidate_pool(args, installed_capability_records()))


def route_selection_capability_payload(record: dict[str, Any]) -> dict[str, Any]:
    capability = record.get("capability", {})
    return {
        "agent": record["agentName"],
        "capability": record["capabilityName"],
        "displayName": record.get("displayName", ""),
        "description": record.get("description", ""),
        "taskTypes": record.get("taskTypes", []),
        "llm": capability.get("llm", {}) if isinstance(capability, dict) else {},
        "configuration": capability.get("configuration", {}) if isinstance(capability, dict) else {},
    }


def build_route_selection_prompt(
    *,
    request: str,
    task_type: str,
    candidates: list[dict[str, Any]],
) -> str:
    payload = {
        "request": request,
        "taskTypeHint": task_type,
        "availableCapabilities": [
            route_selection_capability_payload(record) for record in candidates
        ],
    }
    return "\n".join(
        [
            "Mongoose needs to select one installed agent capability for the user request.",
            "Use only the availableCapabilities list. Do not invent an installed capability.",
            "If no installed capability fits, propose a capability or external tool to add.",
            "Return only one JSON object in one of these forms:",
            '{"action":"select","agent":"AgentName","capability":"capability-name","confidence":0.0,"reason":"short reason"}',
            '{"action":"propose_tool","name":"tool-or-capability-name","description":"what it should do","reason":"why it is needed","requiredInputs":[]}',
            "",
            "Selection input:",
            json.dumps(payload, indent=2, sort_keys=True),
        ]
    )


def find_route_record(
    capabilities: list[dict[str, Any]],
    *,
    agent_name: str,
    capability_name: str,
) -> dict[str, Any] | None:
    for record in capabilities:
        if (
            record["agentName"].lower() == agent_name.lower()
            and record["capabilityName"].lower() == capability_name.lower()
        ):
            return record
    return None


def llm_route_selection(
    args: argparse.Namespace,
    capabilities: list[dict[str, Any]],
) -> dict[str, Any]:
    query = " ".join(args.request or []).strip()
    request = query or str(args.task_type or "").strip()
    if not request:
        return {"ok": False, "reason": "No request was available."}

    profile_name, _profile, profile_error = resolve_llm_profile(None)
    if profile_error:
        return {"ok": False, "reason": "No configured LLM profile is available for route selection."}

    code, payload = invoke_llm_profile(
        profile_name=profile_name,
        prompt=build_route_selection_prompt(
            request=request,
            task_type=str(args.task_type or ""),
            candidates=capabilities,
        ),
        system_prompt=(
            "You select installed Mongoose capabilities. Return strict JSON only. "
            "Prefer an existing capability when it can satisfy the request; otherwise propose the missing tool."
        ),
    )
    if code != 0 or not payload.get("ok"):
        return {"ok": False, "reason": str(payload.get("message", "LLM route selection failed."))}

    content = str(payload.get("response", {}).get("content", "")).strip()
    decision = parse_json_object(content)
    if decision is None:
        return {"ok": False, "reason": "LLM route selection returned invalid JSON."}

    action = str(decision.get("action", "")).strip()
    if action == "select":
        selected = find_route_record(
            capabilities,
            agent_name=str(decision.get("agent", "")).strip(),
            capability_name=str(decision.get("capability", "")).strip(),
        )
        if selected is None:
            return {"ok": False, "reason": "LLM route selection chose a capability that is not installed."}
        return {
            "ok": True,
            "action": "select",
            "record": selected,
            "profile": payload.get("profile", ""),
            "reason": str(decision.get("reason", "")).strip(),
            "confidence": decision.get("confidence", ""),
        }

    if action == "propose_tool":
        return {
            "ok": True,
            "action": "propose_tool",
            "proposal": {
                "name": str(decision.get("name", "")).strip() or "new-capability",
                "description": str(decision.get("description", "")).strip(),
                "reason": str(decision.get("reason", "")).strip(),
                "requiredInputs": string_list(decision.get("requiredInputs", [])),
            },
            "profile": payload.get("profile", ""),
        }

    return {"ok": False, "reason": "LLM route selection did not select or propose a tool."}


def ensure_registry(config: dict[str, Any]) -> Path:
    root = registry_path(config)
    if root.exists():
        return root

    registry_url = config.get("registryUrl", DEFAULT_REGISTRY_URL)
    root.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", registry_url, str(root)])
    return root


def run(command: list[str], cwd: Path | None = None) -> None:
    completed = subprocess.run(command, cwd=str(cwd) if cwd else None, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def capture(command: list[str], cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def registry_revision(root: Path) -> str:
    if not root.exists():
        return "missing"
    if not (root / ".git").exists():
        return "not a git checkout"
    revision = capture(["git", "rev-parse", "--short", "HEAD"], root)
    return revision or "unknown"


def registry_status(root: Path) -> str:
    if not root.exists():
        return "missing"
    if not (root / ".git").exists():
        return "not a git checkout"
    status = capture(["git", "status", "--short"], root)
    if status is None:
        return "unknown"
    return "dirty" if status else "clean"


def local_registry_source(registry_url: str) -> Path | None:
    path = Path(registry_url).expanduser()
    if path.exists():
        return path.resolve()

    parsed = urllib.parse.urlparse(registry_url)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        return path if path.exists() else None

    if parsed.scheme:
        return None
    return None


def parse_release_version(tag_name: str) -> tuple[int, int, int, tuple[str, ...]] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([A-Za-z0-9_.-]+))?", str(tag_name).strip())
    if not match:
        return None
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease


def compare_release_versions(left: str, right: str) -> int:
    left_version = parse_release_version(left)
    right_version = parse_release_version(right)
    if left_version is None or right_version is None:
        raise ValueError("Release versions must be semver-like.")

    left_core = left_version[:3]
    right_core = right_version[:3]
    if left_core != right_core:
        return 1 if left_core > right_core else -1

    left_prerelease = left_version[3]
    right_prerelease = right_version[3]
    if left_prerelease == right_prerelease:
        return 0
    if not left_prerelease:
        return 1
    if not right_prerelease:
        return -1
    return 1 if left_prerelease > right_prerelease else -1


def release_metadata_url() -> str:
    return os.environ.get("MONGOOSE_RELEASES_API_URL", MONGOOSE_RELEASES_API_URL).strip() or MONGOOSE_RELEASES_API_URL


def deferred_self_update_disabled() -> bool:
    value = os.environ.get("MONGOOSE_DISABLE_DEFERRED_SELF_UPDATE", "")
    return value.strip().lower() in {"1", "true", "yes", "always"}


def fetch_release_metadata(url: str | None = None) -> list[dict[str, Any]]:
    url = url or release_metadata_url()
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Mongoose/{MONGOOSE_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read().decode("utf-8")
    except OSError as exc:
        raise SelfUpdateError(f"Could not reach GitHub Releases: {exc}") from exc

    try:
        releases = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SelfUpdateError("GitHub Releases returned invalid JSON.") from exc
    if not isinstance(releases, list):
        raise SelfUpdateError("GitHub Releases returned an unexpected response.")
    return [release for release in releases if isinstance(release, dict)]


def latest_eligible_release(releases: list[dict[str, Any]], include_prerelease: bool = False) -> dict[str, Any] | None:
    eligible: list[dict[str, Any]] = []
    for release in releases:
        tag_name = str(release.get("tag_name", "")).strip()
        if not tag_name or parse_release_version(tag_name) is None:
            continue
        if release.get("draft"):
            continue
        if release.get("prerelease") and not include_prerelease:
            continue
        eligible.append(release)

    if not eligible:
        return None
    return max(eligible, key=lambda release: parse_release_version(str(release["tag_name"])))


def release_asset(release: dict[str, Any], asset_name: str = MONGOOSE_RELEASE_ASSET_NAME) -> dict[str, Any] | None:
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if isinstance(asset, dict) and asset.get("name") == asset_name:
            return asset
    return None


def download_release_asset(asset: dict[str, Any], destination: Path) -> None:
    url = str(asset.get("browser_download_url", "")).strip() or str(asset.get("url", "")).strip()
    if not url:
        raise SelfUpdateError("Release asset did not include a download URL.")

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": f"Mongoose/{MONGOOSE_VERSION}",
        },
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            with destination.open("wb") as file:
                shutil.copyfileobj(response, file)
    except OSError as exc:
        if destination.exists():
            destination.unlink()
        raise SelfUpdateError(f"Could not download {MONGOOSE_RELEASE_ASSET_NAME}: {exc}") from exc

    if not destination.exists() or destination.stat().st_size == 0:
        raise SelfUpdateError(f"Downloaded {MONGOOSE_RELEASE_ASSET_NAME} was empty.")


def installed_mongoose_exe_path() -> Path:
    return USER_BIN / MONGOOSE_RELEASE_ASSET_NAME


def replace_installed_executable(staged_exe: Path, target_exe: Path) -> str:
    target_exe.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(staged_exe, target_exe)
        return "replaced"
    except OSError as exc:
        if not target_exe.exists():
            raise SelfUpdateError(f"Could not install {target_exe}: {exc}") from exc
        if deferred_self_update_disabled():
            raise SelfUpdateError(
                f"Downloaded update to {staged_exe}, but could not replace {target_exe}: {exc}"
            ) from exc
        try:
            schedule_executable_replacement(staged_exe, target_exe)
        except OSError as schedule_exc:
            raise SelfUpdateError(
                f"Downloaded update to {staged_exe}, but could not replace {target_exe}: {exc}"
            ) from schedule_exc
        return "scheduled"


def schedule_executable_replacement(staged_exe: Path, target_exe: Path) -> Path:
    script_path = APP_ROOT / "apply-mongoose-update.ps1"
    script = """param(
    [Parameter(Mandatory=$true)][int]$ProcessId,
    [Parameter(Mandatory=$true)][string]$StagedExe,
    [Parameter(Mandatory=$true)][string]$TargetExe
)
Wait-Process -Id $ProcessId -ErrorAction SilentlyContinue
Move-Item -LiteralPath $StagedExe -Destination $TargetExe -Force
"""
    atomic_write_text(script_path, script)
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script_path),
            "-ProcessId",
            str(os.getpid()),
            "-StagedExe",
            str(staged_exe),
            "-TargetExe",
            str(target_exe),
        ],
        close_fds=True,
    )
    return script_path


def update_mongoose_cli(include_prerelease: bool = False) -> int:
    print_heading("Mongoose CLI update")
    print(label_line("Installed", version_string()))
    try:
        releases = fetch_release_metadata()
        latest_release = latest_eligible_release(releases, include_prerelease=include_prerelease)
        if latest_release is None:
            print_error("No eligible Mongoose releases were found.")
            return 1

        latest_tag = str(latest_release["tag_name"])
        latest_version = latest_tag[1:] if latest_tag.startswith("v") else latest_tag
        print(label_line("Latest", latest_tag))
        if compare_release_versions(MONGOOSE_VERSION, latest_version) >= 0:
            print_success(f"Mongoose is already current: {MONGOOSE_VERSION}")
            return 0

        asset = release_asset(latest_release)
        if asset is None:
            print_error(f"Release {latest_tag} does not include {MONGOOSE_RELEASE_ASSET_NAME}.")
            return 1

        target_exe = installed_mongoose_exe_path()
        staged_exe = APP_ROOT / f".{MONGOOSE_RELEASE_ASSET_NAME}.{latest_tag}.{os.getpid()}.download"
        print(label_line("Download", str(asset.get("browser_download_url", asset.get("url", ""))), "muted"))
        download_release_asset(asset, staged_exe)
        result = replace_installed_executable(staged_exe, target_exe)
    except (SelfUpdateError, ValueError) as exc:
        print_error(str(exc))
        print_muted("Retry later, or download mongoose.exe manually from the GitHub Release.")
        return 1

    if result == "scheduled":
        print_success(f"Downloaded Mongoose {latest_version}; replacement will finish after this command exits.")
    else:
        print_success(f"Updated Mongoose to {latest_version}: {target_exe}")
    print_muted("Run `mongoose --version` in a new terminal to confirm the installed release.")
    return 0


def update_registry() -> int:
    print_heading("Mongoose registry update")
    config = load_config()
    root = registry_path(config)
    registry_url = config.get("registryUrl", DEFAULT_REGISTRY_URL)

    if root.exists() and (root / ".git").exists():
        completed = subprocess.run(["git", "pull", "--ff-only"], cwd=str(root), check=False)
        if completed.returncode != 0:
            print_error(f"Registry update failed at {root}.")
            return completed.returncode
        print_success(f"Updated registry at {root}")
        return 0

    if root.exists():
        print_error(f"Registry path exists but is not a Git repository: {root}")
        return 1

    root.parent.mkdir(parents=True, exist_ok=True)
    local_source = local_registry_source(registry_url)
    if local_source is not None:
        shutil.copytree(
            local_source,
            root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
        print_success(f"Copied local registry to {root}")
        return 0

    completed = subprocess.run(["git", "clone", registry_url, str(root)], check=False)
    if completed.returncode != 0:
        print_error(f"Registry clone failed from {registry_url}.")
        return completed.returncode
    print_success(f"Cloned registry to {root}")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    ensure_state_layout()
    registry_root = Path(args.registry_root).expanduser().resolve()
    config = {
        "registryUrl": args.registry_url,
        "registryPath": str(registry_root),
    }
    save_config(config)
    USER_BIN.mkdir(parents=True, exist_ok=True)

    print_success("Mongoose configured.")
    print(label_line("Registry", registry_root))
    print(label_line("Config", CONFIG_PATH))
    print("")
    print_heading("Try")
    print("mongoose list")
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    paths = ensure_state_layout() if args.init else state_contract()
    if args.cleanup_logs:
        removed = cleanup_logs(args.log_retention_days)
        print_success(f"Removed {len(removed)} expired log file(s).")
        print("")

    if args.json:
        print(json.dumps(paths, indent=2, sort_keys=True))
        return 0

    print_heading("Mongoose local state")
    for name, path in paths.items():
        if name in {"version", "registryStatus"}:
            print(f"  {label_line(name, path, 'success' if path == 'clean' else 'selected')}")
        else:
            print(f"  {label_line(name, path, 'muted')}")
    return 0


def runtime_health_summary() -> dict[str, Any]:
    ensure_state_layout()
    runtime = load_runtime_state()
    jobs = load_job_records()
    active_jobs = [job for job in jobs if job.get("status") == "running"]
    recent_failures = [job for job in jobs if job.get("status") == "failed"][:5]
    installed = load_installed_agents()
    llm_profiles = load_llm_profiles()
    default_llm = str(llm_profiles.get("default", "")).strip()
    llm_status = "not-configured"
    llm_guidance = "No default LLM profile configured. Run: mongoose llm setup"
    llm_ping: dict[str, Any] = {}
    if default_llm:
        _, profile, error = resolve_llm_profile(default_llm)
        if error:
            llm_status = "invalid"
            llm_guidance = "Default LLM profile needs attention. Run: mongoose llm show"
        else:
            llm_ping = http_llm_ping(profile, timeout_seconds=1.5) if profile.get("provider") != "fake" else fake_llm_ping(profile)
            if llm_ping.get("ok"):
                llm_status = "reachable"
                llm_guidance = ""
            else:
                llm_status = "unreachable"
                llm_guidance = "LLM profile configured but unreachable. Run: mongoose llm ping"
    registry = registry_path(load_config())
    return {
        "version": MONGOOSE_VERSION,
        "runtime": runtime,
        "paths": state_contract(),
        "registry": {
            "path": str(registry),
            "revision": registry_revision(registry),
            "status": registry_status(registry),
        },
        "installedAgents": len(installed),
        "installedCapabilities": len(installed_capability_records(installed)),
        "jobs": {
            "total": len(jobs),
            "active": len(active_jobs),
            "recentFailures": len(recent_failures),
            "latest": jobs[0]["id"] if jobs else "",
        },
        "llm": {
            "defaultProfile": default_llm,
            "configuredProfiles": len(llm_profiles.get("profiles", {})) if isinstance(llm_profiles.get("profiles", {}), dict) else 0,
            "status": llm_status,
            "guidance": llm_guidance,
            "pingMessage": llm_ping.get("message", ""),
        },
    }


def print_runtime_health(summary: dict[str, Any]) -> None:
    print_heading("Mongoose status")
    print(label_line("Version", summary["version"]))
    print(label_line("Runtime", summary["runtime"].get("status", "unknown"), "success" if summary["runtime"].get("status") == "running" else "warning"))
    if summary["runtime"].get("message"):
        print(label_line("Runtime note", summary["runtime"]["message"], "muted"))
    print(label_line("Registry", f"{summary['registry']['status']} @ {summary['registry']['revision']}"))
    print(label_line("Installed agents", summary["installedAgents"]))
    print(label_line("Installed capabilities", summary["installedCapabilities"]))
    print(label_line("Jobs", f"{summary['jobs']['total']} total, {summary['jobs']['active']} active, {summary['jobs']['recentFailures']} recent failure(s)"))
    if summary["jobs"].get("latest"):
        print(label_line("Latest job", summary["jobs"]["latest"], "muted"))
    llm_default = summary["llm"].get("defaultProfile") or "none"
    llm_status = summary["llm"].get("status", "not-configured")
    print(label_line("Default LLM", llm_default, "success" if llm_status == "reachable" else "warning"))
    if summary["llm"].get("guidance"):
        print_muted(summary["llm"]["guidance"])


def cmd_status(args: argparse.Namespace) -> int:
    summary = runtime_health_summary()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print_runtime_health(summary)
    return 0


def cmd_runtime_status(args: argparse.Namespace) -> int:
    return cmd_status(args)


def cmd_runtime_start(_: argparse.Namespace) -> int:
    state = save_runtime_state(
        "running",
        "Runtime foundation is marked running. Background daemon execution is planned for scheduler milestones.",
    )
    print_success("Mongoose runtime marked running.")
    print(label_line("Status", state["status"]))
    print(label_line("State", runtime_state_path(), "muted"))
    return 0


def cmd_runtime_stop(_: argparse.Namespace) -> int:
    state = save_runtime_state("stopped", "Runtime foundation is stopped.")
    print_success("Mongoose runtime marked stopped.")
    print(label_line("Status", state["status"]))
    return 0


def cmd_runtime_restart(args: argparse.Namespace) -> int:
    cmd_runtime_stop(args)
    print("")
    return cmd_runtime_start(args)


def cmd_memory_append(args: argparse.Namespace) -> int:
    if args.record_json:
        try:
            payload = json.loads(args.record_json)
        except json.JSONDecodeError as exc:
            print_error(f"Memory record JSON is invalid: {exc}")
            return 1
    elif args.record_file:
        try:
            payload = read_json(Path(args.record_file).expanduser())
        except (OSError, ValueError) as exc:
            print_error(str(exc))
            return 1
    else:
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            print_error(f"Memory record JSON is invalid: {exc}")
            return 1

    if not isinstance(payload, dict):
        print_error("Memory record must be a JSON object.")
        return 1

    record = append_memory_record(payload)
    if args.json:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print_success("Memory record stored.")
        print(label_line("Record", record.get("recordId", "")))
        print(label_line("Type", record.get("recordType", "")))
    return 0


def cmd_memory_list(args: argparse.Namespace) -> int:
    records = query_memory_records(args)
    if args.json:
        print(json.dumps(records, indent=2, sort_keys=True))
        return 0
    if not records:
        print_warning("No memory records found.")
        return 0
    print_heading("Mongoose memory records")
    for record in records:
        agent = record.get("agentId", "")
        capability = f"::{record.get('capabilityId')}" if record.get("capabilityId") else ""
        print(
            f"  {record.get('recordId')}  {record.get('recordType')}  "
            f"{agent}{capability}  {record.get('createdAt', '')}"
        )
    return 0


def cmd_memory_show(args: argparse.Namespace) -> int:
    for record in load_memory_records():
        if str(record.get("recordId", "")) == args.record_id:
            if args.json:
                print(json.dumps(record, indent=2, sort_keys=True))
            else:
                print_heading(f"Memory record: {record.get('recordId')}")
                print(label_line("Type", record.get("recordType", "")))
                print(label_line("Agent", record.get("agentId", "")))
                if record.get("capabilityId"):
                    print(label_line("Capability", record.get("capabilityId", "")))
                print(label_line("Created", record.get("createdAt", ""), "muted"))
                summary = record.get("decision", {}).get("summary") if isinstance(record.get("decision"), dict) else ""
                if summary:
                    print(label_line("Decision", summary))
            return 0
    print_error(f"Memory record '{args.record_id}' was not found.")
    return 1


def cmd_memory_context(args: argparse.Namespace) -> int:
    context = memory_prompt_context(args)
    if args.json:
        print(json.dumps(context, indent=2, sort_keys=True))
        return 0
    print_heading("Mongoose prompt context")
    if context["fallback"]["used"]:
        print_warning(context["fallback"]["message"])
        return 0
    for record in context["records"]:
        print(f"  {record.get('recordId')}  {record.get('recordType')}  {record.get('createdAt', '')}")
        print(f"    {record.get('summary', '')}")
    print_muted("Context is informational only; it cannot approve actions or mutate state.")
    return 0


def cmd_jobs_list(args: argparse.Namespace) -> int:
    jobs = load_job_records()[: args.limit]
    if args.json:
        print(json.dumps(jobs, indent=2, sort_keys=True))
        return 0
    if not jobs:
        print_warning("No Mongoose jobs recorded yet.")
        print_muted("Run an installed agent through `mongoose run` or `mongoose route` to create a job record.")
        return 0
    print_heading("Mongoose jobs")
    for job in jobs:
        capability = f"::{job.get('capability')}" if job.get("capability") else ""
        print(
            f"  {job.get('id')}  {job.get('status')}  "
            f"{job.get('agent', {}).get('commandName', '')}{capability}  "
            f"exit={job.get('exitCode')}  {job.get('startedAt')}"
        )
    return 0


def cmd_jobs_show(args: argparse.Namespace) -> int:
    job = load_job_record(args.id)
    if job is None:
        print_error(f"Job '{args.id}' was not found.")
        return 1
    if args.json:
        print(json.dumps(job, indent=2, sort_keys=True))
        return 0
    print_heading(f"Job: {job.get('id')}")
    print(label_line("Status", job.get("status", ""), "success" if job.get("status") == "succeeded" else "warning"))
    print(label_line("Mode", job.get("mode", "")))
    print(label_line("Agent", job.get("agent", {}).get("commandName", "")))
    if job.get("capability"):
        print(label_line("Capability", job.get("capability")))
    print(label_line("Started", job.get("startedAt", ""), "muted"))
    if job.get("finishedAt"):
        print(label_line("Finished", job.get("finishedAt"), "muted"))
    print(label_line("Exit code", job.get("exitCode")))
    print(label_line("Context", job.get("contextPath", ""), "muted"))
    print(label_line("Log", job.get("logPath", ""), "muted"))
    preview = job.get("outputSummary", {}).get("combinedPreview", "")
    if preview:
        print("")
        print_heading("Output preview")
        print(preview)
    return 0


def cmd_jobs_cancel(args: argparse.Namespace) -> int:
    job = load_job_record(args.id)
    if job is None:
        print_error(f"Job '{args.id}' was not found.")
        return 1
    if job.get("status") != "running":
        print_warning(f"Job '{args.id}' is already {job.get('status')}.")
        return 0
    job["status"] = "cancel-requested"
    job["finishedAt"] = now_utc_iso()
    job["message"] = "Cancellation requested. Direct process cancellation is not available for this runtime foundation."
    write_job_record(job)
    append_job_log(job["id"], job["message"], level="WARNING")
    print_warning(job["message"])
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    installed = load_installed_agents()
    if args.installed:
        if not installed:
            print_warning("No installed agents found.")
            return 0

        print_heading("Installed agents")
        for command_name, agent in sorted(installed.items()):
            version = f" v{agent.get('version')}" if agent.get("version") else ""
            description = agent.get("description")
            line = f"  {command_name}{version}"
            if description:
                line = f"{line} - {description}"
            print(line)
        return 0

    config = load_config()
    root = ensure_registry(config)
    agents = load_agent_registry(root)

    if not agents and not installed:
        print_warning("No installable agents found.")
        return 0

    if agents:
        print_heading("Available agents")
        for command_name, agent in sorted(agents.items()):
            description = agent.get("description")
            installed_marker = " [installed]" if command_name in installed else ""
            if description:
                print(f"  {command_name}{installed_marker} - {description}")
            else:
                print(f"  {command_name}{installed_marker}")

    if installed:
        print("")
        print_heading("Installed agents")
        for command_name, agent in sorted(installed.items()):
            print(f"  {command_name} - {agent.get('sourcePath', '')}")

    return 0


def cmd_capabilities(_: argparse.Namespace) -> int:
    capabilities = installed_capability_records()
    if not capabilities:
        print_warning("No installed capabilities found.")
        print_muted("Install an agent first: mongoose install <agent>")
        return 0

    print_heading("Installed capabilities")
    for record in capabilities:
        line = f"  {format_route_candidate(record)}"
        description = record.get("description")
        if description:
            line = f"{line} - {description}"
        print(line)
        required = required_configuration_names(record["agent"], record["capability"])
        if required:
            print(f"    required config: {', '.join(required)}")
        llm = record["capability"].get("llm", {})
        if isinstance(llm, dict) and llm.get("mode", "none") != "none":
            print(f"    llm: {llm.get('mode')}")
    return 0


def create_agent_launcher(command_name: str, entrypoint: str) -> Path:
    USER_BIN.mkdir(parents=True, exist_ok=True)
    launcher_path = USER_BIN / f"{command_name}.cmd"
    launcher = f'@echo off\npython "{entrypoint}" %*\n'
    launcher_path.write_text(launcher, encoding="ascii")
    return launcher_path


def cmd_install(args: argparse.Namespace) -> int:
    source_agent = load_agent_from_source(args.agent)
    if source_agent is not None:
        agent = source_agent
        agents: dict[str, dict[str, Any]] = {}
    else:
        config = load_config()
        root = ensure_registry(config)
        agents = load_agent_registry(root)
        agent = agents.get(args.agent)

    if agent is None:
        print_error(f"Agent '{args.agent}' does not exist.")
        print("")
        print_heading("Available agents")
        for command_name in sorted(agents):
            print(f"  {command_name}")
        return 1

    launcher_path = create_agent_launcher(agent["commandName"], agent["entrypoint"])
    save_installed_agent(agent, launcher_path)
    print_success(f"Installed {agent['displayName']} as {agent['commandName']}.")
    print(label_line("Launcher", launcher_path, "muted"))
    print(label_line("State", installed_agent_path(agent["commandName"]), "muted"))
    print("")
    print_heading("Try")
    print(agent["commandName"])
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    launcher_path = USER_BIN / f"{args.agent}.cmd"
    state_path = installed_agent_path(args.agent)
    removed = False
    if not launcher_path.exists():
        print_warning(f"Agent command '{args.agent}' is not installed.")
    else:
        launcher_path.unlink()
        print_success(f"Removed {launcher_path}")
        removed = True

    if state_path.exists():
        state_path.unlink()
        print_success(f"Removed {state_path}")
        removed = True

    if not removed:
        print_warning(f"No installed state found for '{args.agent}'.")
    return 0


def print_agent_details(agent: dict[str, Any], installed: bool) -> None:
    print_heading(f"Agent: {agent.get('commandName', '')}")
    print(label_line("ID", agent.get("id", agent.get("commandName", ""))))
    print(label_line("Display name", agent.get("displayName", "")))
    print(label_line("Manifest schema", agent.get("schemaVersion", SUPPORTED_MANIFEST_SCHEMA_VERSION)))
    if agent.get("version"):
        print(label_line("Version", agent["version"]))
    print(label_line("Status", "installed" if installed else "available", "success" if installed else "warning"))
    if agent.get("description"):
        print(label_line("Description", agent["description"]))
    print(label_line("Source", agent.get("sourcePath", ""), "muted"))
    print(label_line("Manifest", agent.get("manifestPath", ""), "muted"))
    print(label_line("Entrypoint", agent.get("entrypoint", ""), "muted"))
    if agent.get("launcherPath"):
        print(label_line("Launcher", agent["launcherPath"], "muted"))
    if agent.get("taskTypes"):
        print(f"Task types: {', '.join(str(item) for item in agent['taskTypes'])}")
    if agent.get("requiredInputs"):
        print(f"Required inputs: {', '.join(str(item) for item in agent['requiredInputs'])}")
    configuration = agent.get("configuration", {})
    if isinstance(configuration, dict) and configuration:
        required_config = string_list(configuration.get("required", []))
        optional_config = string_list(configuration.get("optional", []))
        if required_config:
            print(f"Required config: {', '.join(required_config)}")
        if optional_config:
            print(f"Optional config: {', '.join(optional_config)}")
    llm = agent.get("llm", {})
    if isinstance(llm, dict):
        print(f"LLM mode: {llm.get('mode', 'none')}")
    capabilities = agent.get("capabilities", [])
    print("")
    print_heading("Capabilities")
    if not capabilities:
        print("  none declared")
        return
    for capability in capabilities:
        name = capability.get("name", "")
        description = capability.get("description", "")
        task_types = capability.get("taskTypes", [])
        required_inputs = capability.get("requiredInputs", [])
        configuration = capability.get("configuration", {})
        llm = capability.get("llm", {})
        line = f"  {name}"
        if description:
            line = f"{line} - {description}"
        if task_types:
            line = f"{line} [{', '.join(str(item) for item in task_types)}]"
        print(line)
        if required_inputs:
            print(f"    inputs: {', '.join(str(item) for item in required_inputs)}")
        if isinstance(configuration, dict) and configuration.get("required"):
            print(f"    required config: {', '.join(string_list(configuration.get('required')))}")
        if isinstance(llm, dict) and llm.get("mode", "none") != "none":
            print(f"    llm: {llm.get('mode')}")


def cmd_show(args: argparse.Namespace) -> int:
    installed = load_installed_agent(args.agent)
    if installed is not None:
        print_agent_details(installed, installed=True)
        return 0

    config = load_config()
    root = ensure_registry(config)
    available = load_agent_registry(root).get(args.agent)
    if available is not None:
        print_agent_details(available, installed=False)
        return 0

    print_error(f"Agent '{args.agent}' was not found.")
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    agent = load_installed_agent(args.agent)
    if agent is None:
        print_runtime_error(
            runtime_error(
                "mongoose.agent_not_installed",
                f"Agent '{args.agent}' is not installed. Run: mongoose install {args.agent}",
                agent=args.agent,
            )
        )
        return 1

    required_contract = runtime_contract_requirement(agent)
    if required_contract > SUPPORTED_RUNTIME_CONTRACT_VERSION:
        print_runtime_error(
            runtime_error(
                "mongoose.incompatible_runtime_contract",
                (
                    f"Agent '{args.agent}' requires Mongoose runtime contract {required_contract}, "
                    f"but this CLI supports {SUPPORTED_RUNTIME_CONTRACT_VERSION}."
                ),
                agent=args.agent,
                requiredRuntimeContract=required_contract,
                supportedRuntimeContract=SUPPORTED_RUNTIME_CONTRACT_VERSION,
            )
        )
        return 1

    entrypoint = Path(str(agent.get("entrypoint", "")))
    if not entrypoint.exists():
        print_runtime_error(
            runtime_error(
                "mongoose.entrypoint_missing",
                f"Installed agent entrypoint no longer exists: {entrypoint}",
                agent=args.agent,
                entrypoint=str(entrypoint),
            )
        )
        return 1

    agent_args = args.agent_args or ["ask", str(agent.get("example", "Hello"))]
    return run_agent_with_runtime(
        mode="run",
        agent=agent,
        entrypoint=entrypoint,
        agent_args=agent_args,
    )


def cmd_route(args: argparse.Namespace) -> int:
    installed = load_installed_agents()
    if not installed:
        print_error("No installed agents found.")
        print_muted("Install an agent first: mongoose install <agent>")
        return 1

    all_capabilities = installed_capability_records(installed)
    if not all_capabilities:
        print_error("No installed capabilities found.")
        print_muted("Install agents with manifest capability metadata before routing.")
        return 1

    candidate_capabilities = route_candidate_pool(args, all_capabilities)
    llm_candidate_capabilities = route_candidates_for_llm(args, candidate_capabilities)
    query = " ".join(args.request or []).strip()
    llm_selection = llm_route_selection(args, llm_candidate_capabilities)
    llm_proposal = None
    if llm_selection.get("ok") and llm_selection.get("action") == "select":
        matches = [llm_selection["record"]]
    elif llm_selection.get("ok") and llm_selection.get("action") == "propose_tool":
        matches = []
        llm_proposal = llm_selection.get("proposal", {})
    else:
        matches, query = deterministic_route_candidates(args, candidate_capabilities)

    if not matches:
        print_error("No installed capability can handle that request.")
        if args.task_type:
            print(f"Requested task type: {args.task_type}")
        elif query:
            print(f"Request: {query}")
        if llm_proposal:
            print("")
            print_heading("Suggested capability or tool to add")
            print(label_line("Name", llm_proposal.get("name", "")))
            if llm_proposal.get("description"):
                print(label_line("Description", llm_proposal.get("description", "")))
            if llm_proposal.get("reason"):
                print(label_line("Reason", llm_proposal.get("reason", "")))
            if llm_proposal.get("requiredInputs"):
                print(label_line("Required inputs", ", ".join(llm_proposal.get("requiredInputs", []))))
            if llm_selection.get("profile"):
                print(label_line("LLM selector", llm_selection.get("profile", ""), "muted"))
        print("")
        print_heading("Installed capabilities")
        for record in candidate_capabilities or all_capabilities:
            print(f"  {format_route_candidate(record)}")
        return 1

    if len(matches) > 1:
        print_warning("Ambiguous request. More than one installed capability matched:")
        for record in matches:
            print(f"  {format_route_candidate(record)}")
        print("")
        print_muted("Refine with --agent, --capability, or a more specific --task-type.")
        return 1

    selected = matches[0]
    required_contract = runtime_contract_requirement(selected["agent"], selected["capability"])
    if required_contract > SUPPORTED_RUNTIME_CONTRACT_VERSION:
        print_runtime_error(
            runtime_error(
                "mongoose.incompatible_runtime_contract",
                (
                    f"Selected {format_route_candidate(selected)}, but it requires Mongoose runtime contract "
                    f"{required_contract}; this CLI supports {SUPPORTED_RUNTIME_CONTRACT_VERSION}."
                ),
                selected=format_route_candidate(selected),
                requiredRuntimeContract=required_contract,
                supportedRuntimeContract=SUPPORTED_RUNTIME_CONTRACT_VERSION,
            )
        )
        return 1

    missing = missing_required_configuration(selected["agent"], selected["capability"])
    if missing:
        print_runtime_error(
            runtime_error(
                "mongoose.missing_required_configuration",
                f"Selected {format_route_candidate(selected)}, but required configuration is missing.",
                selected=format_route_candidate(selected),
                missing=missing,
            )
        )
        print_muted("Set the missing environment variables or choose another capability.")
        return 1

    llm = selected["capability"].get("llm", {})
    if isinstance(llm, dict) and llm.get("mode") == "required":
        profile_name = str(llm.get("profile", "")).strip() or None
        resolved_name, _, error = resolve_llm_profile(profile_name)
        if error:
            print_runtime_error(
                runtime_error(
                    "mongoose.provider_unavailable",
                    f"Selected {format_route_candidate(selected)}, but it requires an LLM runtime.",
                    selected=format_route_candidate(selected),
                    provider="llm",
                    profile=resolved_name,
                    reason=error,
                )
            )
            print_muted("Configure and test an LLM profile with: mongoose llm add ...; mongoose llm ping")
            return 1

    entrypoint = Path(str(selected["entrypoint"]))
    if not entrypoint.exists():
        print_runtime_error(
            runtime_error(
                "mongoose.entrypoint_missing",
                f"Selected {format_route_candidate(selected)}, but its entrypoint does not exist: {entrypoint}",
                selected=format_route_candidate(selected),
                entrypoint=str(entrypoint),
            )
        )
        return 1

    agent_args = [selected["capabilityName"], *(args.request or [])]
    print(label_line("Selected", format_route_candidate(selected), "success"))
    if llm_selection.get("ok") and llm_selection.get("action") == "select":
        profile = llm_selection.get("profile", "")
        reason = llm_selection.get("reason", "")
        selector = f"LLM ({profile})" if profile else "LLM"
        print(label_line("Selector", selector, "muted"))
        if reason:
            print(label_line("Selection reason", reason, "muted"))
    if args.dry_run:
        print(label_line("Entrypoint", entrypoint, "muted"))
        print(label_line("Arguments", " ".join(agent_args), "muted"))
        return 0

    return run_agent_with_runtime(
        mode="route",
        agent=selected["agent"],
        capability=selected["capability"],
        route={
            "selected": format_route_candidate(selected),
            "taskType": args.task_type,
            "query": query,
        },
        entrypoint=entrypoint,
        agent_args=agent_args,
    )


def cmd_llm_add(args: argparse.Namespace) -> int:
    name = normalize_profile_name(args.name)
    provider = str(args.provider).strip()
    profile: dict[str, Any] = {
        "provider": provider,
        "model": args.model,
        "endpoint": args.endpoint or "",
        "secret": {
            "mode": "env",
            "env": args.api_key_env or "",
        },
        "capabilities": unique_strings(args.capability or []),
        "createdAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    errors = validate_llm_profile(profile)
    if errors:
        print_runtime_error(
            runtime_error(
                "mongoose.llm_profile_invalid",
                f"LLM profile '{name}' is invalid.",
                profile=name,
                errors=errors,
            )
        )
        return 1

    data = load_llm_profiles()
    profiles = data.setdefault("profiles", {})
    profiles[name] = profile
    if args.default or not data.get("default"):
        data["default"] = name
    save_llm_profiles(data)
    print_success("Mongoose LLM profile configured.")
    print(label_line("Name", name))
    print(label_line("Provider", provider))
    print(label_line("Model", args.model))
    if args.api_key_env:
        print(label_line("API key env", args.api_key_env, "muted"))
    if args.endpoint:
        print(label_line("Endpoint", args.endpoint, "muted"))
    if data.get("default") == name:
        print(label_line("Default", "yes", "success"))
    return 0


def prompt_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    default_label = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{default_label}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "true", "1"}


def normalize_setup_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    aliases = {
        "ollama": "local-http",
        "local": "local-http",
        "local-http": "local-http",
        "openai": "openai",
        "anthropic": "anthropic",
        "fake": "fake",
        "test": "fake",
    }
    if normalized not in aliases:
        raise ValueError("Provider must be one of: ollama, local-http, openai, anthropic, fake.")
    return aliases[normalized]


def ollama_models(endpoint: str, timeout_seconds: float = 2.0) -> tuple[bool, list[str], str]:
    test_models = os.environ.get("MONGOOSE_TEST_OLLAMA_MODELS")
    if test_models is not None:
        models = [model.strip() for model in test_models.split(",") if model.strip()]
        return True, sorted(dict.fromkeys(models)), ""

    request = urllib.request.Request(endpoint, headers={"User-Agent": f"mongoose/{MONGOOSE_VERSION}"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        return False, [], redact_secret_text(str(exc))

    models: list[str] = []
    if isinstance(payload, dict):
        for item in list_value(payload.get("models")):
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if name:
                    models.append(name)
    return True, sorted(dict.fromkeys(models)), ""


def local_ollama_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "Ollama" / "ollama.exe"


def find_ollama_executable() -> Path | None:
    explicit = os.environ.get("MONGOOSE_OLLAMA_BIN", "").strip()
    candidates = [Path(explicit)] if explicit else []
    found = shutil.which("ollama")
    if found:
        candidates.append(Path(found))
    candidates.append(local_ollama_path())
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def run_ollama_command(ollama: Path, args: list[str], timeout_seconds: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ollama), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )


def install_ollama_windows(yes: bool) -> bool:
    if os.name != "nt":
        print_warning("Ollama bootstrap install is currently only automated on Windows.")
        print_muted("Install Ollama manually, then rerun: mongoose llm setup --provider ollama --yes --bootstrap")
        return False
    if not yes and not prompt_yes_no("Ollama was not found. Install Ollama now?", True):
        print_muted("Install Ollama manually, then rerun: mongoose llm setup --provider ollama --yes --bootstrap")
        return False

    print_heading("Install Ollama")
    print_muted(f"Downloading installer from {OLLAMA_WINDOWS_INSTALL_URL}")
    installer = Path(tempfile.gettempdir()) / "mongoose-ollama-install.ps1"
    try:
        urllib.request.urlretrieve(OLLAMA_WINDOWS_INSTALL_URL, installer)
    except OSError as exc:
        print_warning("Could not download the Ollama installer.")
        print_muted(redact_secret_text(str(exc)))
        print_muted("Manual install command: irm https://ollama.com/install.ps1 | iex")
        return False

    completed = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(installer)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print_warning("Ollama installer did not complete successfully.")
        output = (completed.stderr or completed.stdout).strip()
        if output:
            print_muted(redact_secret_text(output))
        print_muted("Manual install command: irm https://ollama.com/install.ps1 | iex")
        return False
    print_success("Ollama installed.")
    return True


def start_ollama_service(ollama: Path) -> None:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        subprocess.Popen(
            [str(ollama), "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
        )
    except OSError as exc:
        print_warning("Could not start Ollama automatically.")
        print_muted(redact_secret_text(str(exc)))


def wait_for_ollama(endpoint: str, timeout_seconds: float = 10.0) -> tuple[bool, list[str], str]:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        reachable, models, error = ollama_models(endpoint, timeout_seconds=1.0)
        if reachable:
            return True, models, ""
        last_error = error
        time.sleep(0.5)
    return False, [], last_error


def ollama_model_available(model: str, models: list[str]) -> bool:
    requested = model.strip()
    if not requested:
        return False
    return any(installed == requested or installed == f"{requested}:latest" for installed in models)


def bootstrap_ollama(endpoint: str, model: str, yes: bool) -> tuple[bool, list[str]]:
    print_heading("Ollama bootstrap")
    ollama = find_ollama_executable()
    if not ollama:
        if not install_ollama_windows(yes):
            return False, []
        ollama = find_ollama_executable()
    if not ollama:
        print_warning("Ollama is still not available after installation.")
        print_muted(f"Expected Windows path: {local_ollama_path()}")
        return False, []

    print(label_line("Ollama", ollama, "muted"))
    reachable, models, error = ollama_models(endpoint, timeout_seconds=2.0)
    if not reachable:
        print_muted("Starting Ollama service...")
        start_ollama_service(ollama)
        reachable, models, error = wait_for_ollama(endpoint)
    if not reachable:
        print_warning("Ollama is installed but the local endpoint is not reachable.")
        print_muted(f"Endpoint error: {error}")
        print_muted(f"Try manually: & \"{ollama}\" serve")
        return False, []

    if not ollama_model_available(model, models):
        print_muted(f"Pulling Ollama model: {model}")
        try:
            completed = run_ollama_command(ollama, ["pull", model], timeout_seconds=1800.0)
        except subprocess.TimeoutExpired:
            print_warning("Ollama model pull timed out.")
            print_muted(f"Try manually: & \"{ollama}\" pull {model}")
            return False, models
        if completed.returncode != 0:
            print_warning(f"Ollama could not pull model '{model}'.")
            output = (completed.stderr or completed.stdout).strip()
            if output:
                print_muted(redact_secret_text(output))
            print_muted(f"Try manually: & \"{ollama}\" pull {model}")
            return False, models
        reachable, models, _ = ollama_models(endpoint, timeout_seconds=2.0)
    else:
        print_success(f"Ollama model already installed: {model}")
    return True, models


def warm_llm_profile(name: str, timeout_seconds: float | None) -> int:
    prompt = "Reply with only: ready"
    first_timeout = timeout_seconds if timeout_seconds is not None else DEFAULT_LOCAL_LLM_INVOKE_TIMEOUT_SECONDS
    warmup_timeout = max(first_timeout, DEFAULT_LOCAL_LLM_WARMUP_TIMEOUT_SECONDS)
    print_muted(f"Warming local model with timeout: {warmup_timeout:g} seconds")
    for timeout in (first_timeout, warmup_timeout):
        code, payload = invoke_llm_profile(profile_name=name, prompt=prompt, timeout_seconds=timeout)
        if code == 0:
            print_success("LLM provider invocation verified.")
            content = payload.get("response", {}).get("content", "") if isinstance(payload.get("response"), dict) else ""
            if content:
                print(label_line("Response", content))
            return 0
        if timeout >= warmup_timeout:
            message = str(payload.get("message", "LLM provider invocation failed."))
            print_warning(message)
            return code
        message = str(payload.get("message", ""))
        if "timed out" in message.lower():
            print_muted("Initial local model invocation timed out; retrying with a longer warmup timeout.")
        else:
            print_muted("Initial local model invocation did not complete; retrying with a longer warmup timeout.")
    return 1


def save_llm_profile_from_setup(
    *,
    name: str,
    provider: str,
    model: str,
    endpoint: str = "",
    api_key_env: str = "",
    make_default: bool = False,
) -> tuple[int, dict[str, Any]]:
    profile = {
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "secret": {
            "mode": "env",
            "env": api_key_env,
        },
        "capabilities": [],
        "createdAt": now_utc_iso(),
        "configuredBy": "mongoose llm setup",
    }
    errors = validate_llm_profile(profile)
    if errors:
        print_runtime_error(
            runtime_error(
                "mongoose.llm_profile_invalid",
                f"LLM profile '{name}' is invalid.",
                profile=name,
                errors=errors,
            )
        )
        return 1, profile
    data = load_llm_profiles()
    profiles = data.setdefault("profiles", {})
    profiles[name] = profile
    if make_default or not data.get("default"):
        data["default"] = name
    save_llm_profiles(data)
    return 0, profile


def cmd_llm_setup(args: argparse.Namespace) -> int:
    print_heading("Mongoose LLM setup")
    raw_provider = args.provider or ("ollama" if args.yes else prompt_text("Provider (ollama, openai, anthropic, fake)", "ollama"))
    provider = normalize_setup_provider(raw_provider)
    display_provider = "ollama" if raw_provider.strip().lower() == "ollama" else provider

    default_name = {
        "local-http": "ollama-local" if display_provider == "ollama" else "local-http",
        "openai": "openai-main",
        "anthropic": "anthropic-main",
        "fake": "fake-main",
    }[provider]
    name = normalize_profile_name(args.name or (default_name if args.yes else prompt_text("Profile name", default_name)))

    endpoint = args.endpoint or ""
    model = args.model or ""
    api_key_env = args.api_key_env or ""

    if provider == "local-http":
        endpoint = endpoint or (DEFAULT_OLLAMA_TAGS_ENDPOINT if args.yes else prompt_text("Local HTTP endpoint", DEFAULT_OLLAMA_TAGS_ENDPOINT))
        model = model or (DEFAULT_OLLAMA_MODEL if args.bootstrap else "")
        if args.bootstrap:
            if display_provider != "ollama" and not args.yes and not prompt_yes_no("Bootstrap Ollama for this local HTTP profile?", True):
                print_muted("Skipped Ollama bootstrap.")
            else:
                ok, models = bootstrap_ollama(endpoint, model, args.yes)
                if not ok:
                    return 1
                if models:
                    print(label_line("Available models", ", ".join(models)))
        reachable, models, error = ollama_models(endpoint)
        if reachable:
            print_success("Local LLM endpoint reachable.")
            if models:
                print(label_line("Available models", ", ".join(models)))
                model = model or (models[0] if args.yes else prompt_text("Model", models[0]))
            else:
                print_warning("No local models were reported by the endpoint.")
                print_muted(f"For Ollama, install a model with: ollama pull {DEFAULT_OLLAMA_MODEL}")
                print_muted("Or let Mongoose bootstrap it with: mongoose llm setup --provider ollama --yes --bootstrap")
                model = model or (DEFAULT_OLLAMA_MODEL if args.yes else prompt_text("Model to configure", DEFAULT_OLLAMA_MODEL))
        else:
            print_warning("Local LLM endpoint was not reachable.")
            print_muted(f"Endpoint error: {error}")
            print_muted(f"For Ollama, start Ollama and install a model with: ollama pull {DEFAULT_OLLAMA_MODEL}")
            print_muted("Or let Mongoose bootstrap it with: mongoose llm setup --provider ollama --yes --bootstrap")
            model = model or (DEFAULT_OLLAMA_MODEL if args.yes else prompt_text("Model to configure", DEFAULT_OLLAMA_MODEL))
    elif provider == "fake":
        model = model or ("fake-chat" if args.yes else prompt_text("Model", "fake-chat"))
    elif provider == "openai":
        model = model or ("gpt-4.1-mini" if args.yes else prompt_text("Model", "gpt-4.1-mini"))
        api_key_env = api_key_env or ("OPENAI_API_KEY" if args.yes else prompt_text("API key environment variable", "OPENAI_API_KEY"))
    elif provider == "anthropic":
        model = model or ("claude-3-5-sonnet-latest" if args.yes else prompt_text("Model", "claude-3-5-sonnet-latest"))
        api_key_env = api_key_env or ("ANTHROPIC_API_KEY" if args.yes else prompt_text("API key environment variable", "ANTHROPIC_API_KEY"))

    if api_key_env:
        if os.environ.get(api_key_env):
            print_success(f"Environment variable {api_key_env} is set.")
        else:
            print_warning(f"Environment variable {api_key_env} is not set in this terminal.")
            print_muted(f"Set it before pinging this profile: $env:{api_key_env}='<secret>'")

    make_default = args.default or args.yes or prompt_yes_no("Make this the default LLM profile?", True)
    code, profile = save_llm_profile_from_setup(
        name=name,
        provider=provider,
        model=model,
        endpoint=endpoint,
        api_key_env=api_key_env,
        make_default=make_default,
    )
    if code != 0:
        return code

    print_success("Mongoose LLM profile configured.")
    print(label_line("Name", name))
    print(label_line("Provider", provider))
    print(label_line("Model", model))
    if endpoint:
        print(label_line("Endpoint", endpoint, "muted"))
    if api_key_env:
        print(label_line("API key env", api_key_env, "muted"))
    print(label_line("Default", "yes" if make_default or load_llm_profiles().get("default") == name else "no"))

    if args.skip_ping:
        print_muted("Skipped LLM ping.")
        return 0

    print("")
    print_heading("Ping")
    ping_args = argparse.Namespace(name=name, timeout=effective_llm_ping_timeout(args.timeout))
    result = cmd_llm_ping(ping_args)
    if result != 0:
        print_muted("Review the diagnostics above, then rerun: mongoose llm ping " + name)
        return result

    if provider == "local-http":
        print("")
        print_heading("Warmup")
        return warm_llm_profile(name, args.timeout)
    return 0


def cmd_llm_use(args: argparse.Namespace) -> int:
    name = normalize_profile_name(args.name)
    data = load_llm_profiles()
    profiles = data.get("profiles", {})
    if not isinstance(profiles, dict) or name not in profiles:
        print_runtime_error(
            runtime_error("mongoose.llm_profile_missing", f"LLM profile '{name}' was not found.", profile=name)
        )
        return 1
    data["default"] = name
    save_llm_profiles(data)
    print_success("Default Mongoose LLM profile selected.")
    print(label_line("Default", name))
    return 0


def cmd_llm_list(_: argparse.Namespace) -> int:
    data = load_llm_profiles()
    profiles = data.get("profiles", {})
    default = str(data.get("default", "")).strip()
    if not isinstance(profiles, dict) or not profiles:
        print_warning("No LLM profiles configured.")
        print_muted("Add one with: mongoose llm add <name> --provider fake --model test")
        return 0

    print_heading("Mongoose LLM profiles")
    for name, profile in sorted(profiles.items()):
        if not isinstance(profile, dict):
            continue
        marker = " [default]" if name == default else ""
        summary = llm_profile_summary(name, profile)
        print(f"  {name}{marker} - {summary['provider']} / {summary['model']}")
        if summary.get("apiKeyEnv"):
            status = "set" if summary.get("secretAvailable") else "missing"
            print(f"    api key env: {summary['apiKeyEnv']} ({status})")
        if summary.get("endpoint"):
            print(f"    endpoint: {summary['endpoint']}")
    return 0


def cmd_llm_show(args: argparse.Namespace) -> int:
    name, profile, error = resolve_llm_profile(args.name)
    if error:
        print_runtime_error(error)
        return 1
    summary = llm_profile_summary(name, profile)
    print_heading(f"LLM profile: {name}")
    print(label_line("Provider", summary["provider"]))
    print(label_line("Model", summary["model"]))
    if summary.get("endpoint"):
        print(label_line("Endpoint", summary["endpoint"], "muted"))
    if summary.get("apiKeyEnv"):
        print(label_line("API key env", summary["apiKeyEnv"], "muted"))
        print(label_line("Secret available", "yes" if summary["secretAvailable"] else "no", "success" if summary["secretAvailable"] else "warning"))
    if summary.get("capabilities"):
        print(label_line("Capabilities", ", ".join(summary["capabilities"])))
    return 0


def fake_llm_ping(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "message": "Fake LLM provider reachable.",
        "response": {
            "role": "assistant",
            "content": "pong",
            "model": profile.get("model", ""),
        },
    }


def fake_llm_invoke(profile: dict[str, Any], messages: list[dict[str, str]]) -> dict[str, Any]:
    user_text = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            user_text = message.get("content", "")
            break
    request_text = user_text
    if "Selection input:" in user_text:
        selection_payload = parse_json_object(user_text.split("Selection input:", 1)[1])
        if isinstance(selection_payload, dict) and selection_payload.get("request") is not None:
            request_text = str(selection_payload.get("request", ""))
    lowered_request = request_text.lower()

    if "Njord needs to select one installed capability" in user_text:
        if "weekly" in lowered_request or "brief" in lowered_request:
            selected = "brief"
        elif "spending" in lowered_request or "transactions" in lowered_request or "cash flow" in lowered_request:
            selected = "ynab-spending-review"
        elif "risk" in lowered_request or "forecast" in lowered_request or "finance review" in lowered_request or "review my finances" in lowered_request:
            selected = "finance-review"
        elif "config" in lowered_request or "credential" in lowered_request:
            selected = "config-status"
        elif "hello" in lowered_request or "connection" in lowered_request:
            selected = "hello-world"
        else:
            selected = "ynab-budget-summary"
        content = json.dumps(
            {
                "capability": selected,
                "confidence": 0.9,
                "reason": "Selected by the fake configured LLM for validation.",
            },
            sort_keys=True,
        )
    elif "Mongoose needs to select one installed agent capability" in user_text:
        lowered = user_text.lower()
        if "weather" in lowered_request or "calendar" in lowered_request:
            content = json.dumps(
                {
                    "action": "propose_tool",
                    "name": "weather-lookup",
                    "description": "Look up current weather and forecasts for a requested location.",
                    "reason": "No installed capability exposes weather data.",
                    "requiredInputs": ["location"],
                },
                sort_keys=True,
            )
        elif '"agent": "Njord"' in user_text and '"capability": "brief"' in user_text and (
            "weekly" in lowered_request or "brief" in lowered_request
        ):
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Njord",
                    "capability": "brief",
                    "confidence": 0.92,
                    "reason": "The request asks for a weekly financial brief.",
                },
                sort_keys=True,
            )
        elif '"agent": "Njord"' in user_text and '"capability": "ynab-spending-review"' in user_text and (
            "spending" in lowered_request or "transactions" in lowered_request or "cash flow" in lowered_request
        ):
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Njord",
                    "capability": "ynab-spending-review",
                    "confidence": 0.92,
                    "reason": "The request asks about spending or transactions.",
                },
                sort_keys=True,
            )
        elif '"agent": "Njord"' in user_text and '"capability": "finance-review"' in user_text and (
            "risk" in lowered_request or "forecast" in lowered_request or "review my finances" in lowered_request
        ):
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Njord",
                    "capability": "finance-review",
                    "confidence": 0.92,
                    "reason": "The request asks for a finance review.",
                },
                sort_keys=True,
            )
        elif '"agent": "Njord"' in user_text and '"capability": "ynab-budget-summary"' in user_text and (
            "budget" in lowered_request or "summary" in lowered_request or "ynab" in lowered_request
        ):
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Njord",
                    "capability": "ynab-budget-summary",
                    "confidence": 0.88,
                    "reason": "The request asks for a budget summary.",
                },
                sort_keys=True,
            )
        elif '"agent": "Njord"' in user_text and '"capability": "config-status"' in user_text:
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Njord",
                    "capability": "config-status",
                    "confidence": 0.93,
                    "reason": "The request asks for configuration status.",
                },
                sort_keys=True,
            )
        elif '"capability": "report"' in lowered and "summary" in lowered_request:
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Beta",
                    "capability": "report",
                    "confidence": 0.92,
                    "reason": "The request asks for a report or summary.",
                },
                sort_keys=True,
            )
        elif '"capability": "plan"' in lowered and ("build" in lowered_request or "steps" in lowered_request):
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Alpha",
                    "capability": "plan",
                    "confidence": 0.9,
                    "reason": "The request asks for work planning.",
                },
                sort_keys=True,
            )
        elif '"capability": "llm-ready"' in lowered:
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Alpha",
                    "capability": "llm-ready",
                    "confidence": 0.95,
                    "reason": "The task type is constrained to the LLM-ready capability.",
                },
                sort_keys=True,
            )
        elif '"capability": "llm-only"' in lowered:
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Alpha",
                    "capability": "llm-only",
                    "confidence": 0.95,
                    "reason": "The task type is constrained to the LLM-only capability.",
                },
                sort_keys=True,
            )
        elif '"capability": "secure"' in lowered:
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Alpha",
                    "capability": "secure",
                    "confidence": 0.95,
                    "reason": "The task type is constrained to the secure capability.",
                },
                sort_keys=True,
            )
        elif '"capability": "future"' in lowered or '"capability": "future-runtime"' in lowered:
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "FutureRuntime",
                    "capability": "future",
                    "confidence": 0.95,
                    "reason": "The task type is constrained to the future runtime capability.",
                },
                sort_keys=True,
            )
        elif '"capability": "echo"' in lowered:
            content = json.dumps(
                {
                    "action": "select",
                    "agent": "Alpha",
                    "capability": "echo",
                    "confidence": 0.6,
                    "reason": "The request fits the generic echo diagnostic capability.",
                },
                sort_keys=True,
            )
        else:
            content = json.dumps(
                {
                    "action": "propose_tool",
                    "name": "new-capability",
                    "description": "Add a capability that can handle the requested work.",
                    "reason": "The installed capability metadata does not cover the request.",
                    "requiredInputs": [],
                },
                sort_keys=True,
            )
    else:
        trimmed = " ".join(user_text.split())[:160]
        content = f"Fake LLM narration based on deterministic context: {trimmed}"
    return {
        "ok": True,
        "message": "Fake LLM provider invoked.",
        "response": {
            "role": "assistant",
            "content": content,
            "model": profile.get("model", ""),
        },
    }


def llm_profile_provider(profile: dict[str, Any]) -> str:
    return str(profile.get("provider", "")).strip()


def is_local_llm_profile(profile: dict[str, Any]) -> bool:
    return llm_profile_provider(profile) == "local-http"


def effective_llm_ping_timeout(timeout_seconds: float | None) -> float:
    return timeout_seconds if timeout_seconds is not None else DEFAULT_LLM_PING_TIMEOUT_SECONDS


def effective_llm_invoke_timeout(profile: dict[str, Any], timeout_seconds: float | None) -> float:
    if timeout_seconds is not None:
        return timeout_seconds
    if is_local_llm_profile(profile):
        return DEFAULT_LOCAL_LLM_INVOKE_TIMEOUT_SECONDS
    return DEFAULT_REMOTE_LLM_INVOKE_TIMEOUT_SECONDS


def http_llm_ping(profile: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    provider = llm_profile_provider(profile)
    endpoint = str(profile.get("endpoint", "")).strip()
    secret = profile.get("secret", {}) if isinstance(profile.get("secret", {}), dict) else {}
    api_key = os.environ.get(str(secret.get("env", "")).strip(), "")
    headers = {"User-Agent": f"mongoose/{MONGOOSE_VERSION}"}
    if provider == "openai":
        endpoint = endpoint or "https://api.openai.com/v1/models"
        headers["Authorization"] = f"Bearer {api_key}"
    elif provider == "anthropic":
        endpoint = endpoint or "https://api.anthropic.com/v1/messages"
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"

    request = urllib.request.Request(endpoint, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 200)
            return {"ok": 200 <= status < 300, "status": status, "message": "LLM provider reachable."}
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "message": "LLM provider returned an HTTP error.",
        }
    except TimeoutError:
        return {"ok": False, "message": "LLM provider ping timed out."}
    except OSError as exc:
        return {"ok": False, "message": redact_secret_text(str(exc))}


def http_llm_invoke(profile: dict[str, Any], messages: list[dict[str, str]], timeout_seconds: float) -> dict[str, Any]:
    provider = llm_profile_provider(profile)
    endpoint = str(profile.get("endpoint", "")).strip()
    model = str(profile.get("model", "")).strip()
    secret = profile.get("secret", {}) if isinstance(profile.get("secret", {}), dict) else {}
    api_key = os.environ.get(str(secret.get("env", "")).strip(), "")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"mongoose/{MONGOOSE_VERSION}",
    }
    payload: dict[str, Any]

    if provider == "openai":
        endpoint = endpoint or "https://api.openai.com/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 500,
        }
    elif provider == "anthropic":
        endpoint = endpoint or "https://api.anthropic.com/v1/messages"
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        system = "\n".join(message["content"] for message in messages if message.get("role") == "system")
        anthropic_messages = [
            {"role": message.get("role", "user"), "content": message.get("content", "")}
            for message in messages
            if message.get("role") != "system"
        ]
        payload = {
            "model": model,
            "system": system,
            "messages": anthropic_messages,
            "max_tokens": 500,
        }
    else:
        if endpoint.endswith("/api/tags"):
            endpoint = endpoint[: -len("/api/tags")] + "/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 200)
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "message": "LLM provider returned an HTTP error.",
        }
    except TimeoutError:
        return {"ok": False, "message": "LLM provider invocation timed out."}
    except OSError as exc:
        return {"ok": False, "message": redact_secret_text(str(exc))}

    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {"ok": False, "status": status, "message": "LLM provider returned invalid JSON."}

    content = ""
    if provider == "openai":
        choices = data.get("choices", []) if isinstance(data, dict) else []
        first = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = first.get("message", {}) if isinstance(first.get("message", {}), dict) else {}
        content = str(message.get("content", "")).strip()
    elif provider == "anthropic":
        blocks = data.get("content", []) if isinstance(data, dict) else []
        parts = [str(block.get("text", "")).strip() for block in blocks if isinstance(block, dict)]
        content = "\n".join(part for part in parts if part)
    else:
        message = data.get("message", {}) if isinstance(data, dict) and isinstance(data.get("message", {}), dict) else {}
        content = str(message.get("content") or data.get("response", "") if isinstance(data, dict) else "").strip()

    if not content:
        return {"ok": False, "status": status, "message": "LLM provider returned an empty response."}
    return {
        "ok": 200 <= status < 300,
        "status": status,
        "message": "LLM provider invoked.",
        "response": {
            "role": "assistant",
            "content": content,
            "model": model,
        },
    }


def invoke_llm_profile(
    *,
    profile_name: str | None,
    prompt: str,
    system_prompt: str = "",
    timeout_seconds: float | None = None,
) -> tuple[int, dict[str, Any]]:
    name, profile, error = resolve_llm_profile(profile_name)
    if error:
        return 1, {
            "ok": False,
            "error": error,
            "profile": name,
            "response": {},
        }

    messages: list[dict[str, str]] = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": prompt})

    start = time.perf_counter()
    provider = llm_profile_provider(profile)
    invoke_timeout = effective_llm_invoke_timeout(profile, timeout_seconds)
    if provider == "fake":
        result = fake_llm_invoke(profile, messages)
    else:
        result = http_llm_invoke(profile, messages, timeout_seconds=invoke_timeout)
    latency_ms = int((time.perf_counter() - start) * 1000)

    response = result.get("response", {}) if isinstance(result.get("response", {}), dict) else {}
    payload = {
        "ok": bool(result.get("ok")),
        "profile": name,
        "provider": provider,
        "model": profile.get("model", ""),
        "latencyMs": latency_ms,
        "message": str(result.get("message", "")),
        "response": {
            "role": response.get("role", "assistant"),
            "content": redact_secret_text(str(response.get("content", ""))),
            "model": response.get("model", profile.get("model", "")),
        },
    }
    if result.get("status") not in (None, ""):
        payload["status"] = result.get("status")
    if not result.get("ok"):
        payload["error"] = runtime_error(
            "mongoose.llm_invoke_failed",
            str(result.get("message", "LLM provider invocation failed.")),
            profile=name,
            provider=provider,
            status=result.get("status", ""),
        )
        return 1, payload
    return 0, payload


def cmd_llm_invoke(args: argparse.Namespace) -> int:
    prompt = " ".join(args.prompt or []).strip()
    if not prompt:
        prompt = sys.stdin.read().strip()
    if not prompt:
        print_error("llm invoke requires prompt text from arguments or stdin.")
        return 1

    code, payload = invoke_llm_profile(
        profile_name=args.profile,
        prompt=prompt,
        system_prompt=args.system or "",
        timeout_seconds=args.timeout,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return code

    if payload.get("ok"):
        print_success("LLM provider invoked.")
        print(label_line("Profile", payload.get("profile", "")))
        print(label_line("Provider", payload.get("provider", "")))
        print(label_line("Model", payload.get("model", "")))
        print(label_line("Latency", f"{payload.get('latencyMs', 0)} ms", "muted"))
        print("")
        print(str(payload.get("response", {}).get("content", "")))
        return 0

    error = payload.get("error")
    if isinstance(error, dict):
        print_runtime_error(error)
    else:
        print_error(str(payload.get("message", "LLM provider invocation failed.")))
    return code


def cmd_llm_ping(args: argparse.Namespace) -> int:
    name, profile, error = resolve_llm_profile(args.name)
    if error:
        print_runtime_error(error)
        return 1

    start = time.perf_counter()
    provider = llm_profile_provider(profile)
    timeout = effective_llm_ping_timeout(args.timeout)
    if provider == "fake":
        result = fake_llm_ping(profile)
    else:
        result = http_llm_ping(profile, timeout_seconds=timeout)
    latency_ms = int((time.perf_counter() - start) * 1000)

    if result.get("ok"):
        print_success("LLM provider reachable.")
    else:
        print_runtime_error(
            runtime_error(
                "mongoose.llm_ping_failed",
                str(result.get("message", "LLM provider ping failed.")),
                profile=name,
                provider=provider,
                status=result.get("status", ""),
            )
        )
    print(label_line("Profile", name))
    print(label_line("Provider", provider))
    print(label_line("Model", profile.get("model", "")))
    print(label_line("Latency", f"{latency_ms} ms", "muted"))
    if provider == "fake" and isinstance(result.get("response"), dict):
        print(label_line("Response", result["response"].get("content", ""), "muted"))
    return 0 if result.get("ok") else 1


def cmd_update(args: argparse.Namespace) -> int:
    if args.registry_only and args.include_prerelease:
        print_error("--include-prerelease can only be used when checking the Mongoose CLI update phase.")
        return 1

    if args.self_only:
        return update_mongoose_cli(include_prerelease=args.include_prerelease)

    if args.registry_only:
        return update_registry()

    print_heading("Mongoose update")
    registry_code = update_registry()
    print("")
    cli_code = update_mongoose_cli(include_prerelease=args.include_prerelease)
    print("")
    print_heading("Update summary")
    print(label_line("Registry", "ok" if registry_code == 0 else f"failed ({registry_code})", "success" if registry_code == 0 else "error"))
    print(label_line("Mongoose CLI", "ok" if cli_code == 0 else f"failed ({cli_code})", "success" if cli_code == 0 else "error"))
    return 0 if registry_code == 0 and cli_code == 0 else 1


def cmd_validate(args: argparse.Namespace) -> int:
    if args.path:
        root = Path(args.path).expanduser().resolve()
    else:
        config = load_config()
        root = ensure_registry(config)

    manifest_path = root if root.is_file() else root / "agent.json"
    if manifest_path.exists() and manifest_path.is_file():
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict):
            raise ManifestValidationError(manifest_path, ["Manifest must be a JSON object."])
        validate_manifest(manifest, manifest_path)
        print_success(f"Manifest valid: {manifest_path}")
        return 0

    manifests = agent_manifest_paths(root)
    if not manifests:
        print_error(f"No agent manifests found under {root}")
        return 1

    for path in manifests:
        manifest = read_json(path)
        if not isinstance(manifest, dict):
            raise ManifestValidationError(path, ["Manifest must be a JSON object."])
        validate_manifest(manifest, path)
        print_success(f"Manifest valid: {path}")
    print_success(f"Validated {len(manifests)} manifest(s).")
    return 0


def relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def architecture_output_root(root: Path, output_root: str | None = None) -> Path:
    if output_root:
        return Path(output_root).expanduser().resolve()
    return root / "docs" / "architecture"


def architecture_output_paths(root: Path, output_root: str | None = None) -> dict[str, Path]:
    base = architecture_output_root(root, output_root)
    return {
        "model": base / "model.json",
        "agents_sysml": base / "sysml" / "agents.sysml",
        "runtime_sysml": base / "sysml" / "runtime-routing.sysml",
        "agents_mermaid": base / "diagrams" / "agents.mmd",
        "runtime_mermaid": base / "diagrams" / "runtime-routing.mmd",
        "providers_mermaid": base / "diagrams" / "providers.mmd",
    }


def normalize_architecture_id(value: str, fallback: str) -> str:
    raw = value.strip() or fallback
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", raw)
    normalized = normalized.strip("_")
    if not normalized:
        normalized = fallback
    if not normalized[0].isalpha():
        normalized = f"A_{normalized}"
    return normalized


def mermaid_id(value: str, fallback: str) -> str:
    return normalize_architecture_id(value, fallback)


def mermaid_label(value: str) -> str:
    return str(value).replace('"', "'")


def sysml_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def config_names(metadata: dict[str, Any]) -> dict[str, list[str]]:
    configuration = metadata.get("configuration", {})
    if not isinstance(configuration, dict):
        configuration = {}
    required = string_list(configuration.get("required"))
    optional = string_list(configuration.get("optional"))
    if not required:
        required = string_list(metadata.get("requiredInputs"))
    return {
        "required": sorted(dict.fromkeys(required)),
        "optional": sorted(dict.fromkeys(optional)),
        "secretRefs": sorted(dict.fromkeys(string_list(configuration.get("secretRefs")))),
    }


def capability_architecture(agent_dir: Path, root: Path, manifest: dict[str, Any], capability: dict[str, Any]) -> dict[str, Any]:
    name = str(capability.get("name", "")).strip()
    display_name = str(capability.get("displayName", name)).strip() or name
    entrypoint = str(capability.get("entrypointPath", manifest.get("entrypointPath", "agent.py"))).strip()
    requires = capability.get("requires", {})
    if not isinstance(requires, dict):
        requires = {}
    llm = capability.get("llm", manifest.get("llm", {}))
    if not isinstance(llm, dict):
        llm = {}
    return {
        "name": name,
        "id": normalize_architecture_id(name, "Capability"),
        "displayName": display_name,
        "description": str(capability.get("description", "")).strip(),
        "entrypointPath": relative_posix(agent_dir / entrypoint, root),
        "taskTypes": sorted(dict.fromkeys(string_list(capability.get("taskTypes")))),
        "configuration": config_names(capability),
        "requires": requires,
        "llm": {
            "mode": str(llm.get("mode", "unspecified")).strip() or "unspecified",
            "deterministicFallback": str(llm.get("deterministicFallback", "")).strip(),
        },
    }


def build_architecture_model(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    manifests = agent_manifest_paths(root)
    if not manifests:
        raise ValueError(f"No agent manifests found under {root}")

    agents: list[dict[str, Any]] = []
    for manifest_path in manifests:
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict):
            raise ManifestValidationError(manifest_path, ["Manifest must be a JSON object."])
        validate_manifest(manifest, manifest_path)

        agent_dir = manifest_path.parent
        agent_name = str(manifest.get("commandName", manifest_path.parent.name)).strip()
        agent_id = str(manifest.get("id", manifest_path.parent.name)).strip()
        requires = manifest.get("requires", {})
        if not isinstance(requires, dict):
            requires = {}
        llm = manifest.get("llm", {})
        if not isinstance(llm, dict):
            llm = {}
        capabilities = [
            capability_architecture(agent_dir, root, manifest, capability)
            for capability in list_value(manifest.get("capabilities"))
            if isinstance(capability, dict) and str(capability.get("name", "")).strip()
        ]
        agents.append(
            {
                "id": normalize_architecture_id(agent_id, "Agent"),
                "manifestId": agent_id,
                "commandName": agent_name,
                "displayName": str(manifest.get("displayName", agent_name)).strip() or agent_name,
                "version": str(manifest.get("version", "")).strip(),
                "description": str(manifest.get("description", "")).strip(),
                "manifestPath": relative_posix(manifest_path, root),
                "entrypointPath": relative_posix(agent_dir / str(manifest.get("entrypointPath", "agent.py")).strip(), root),
                "taskTypes": sorted(dict.fromkeys(string_list(manifest.get("taskTypes")))),
                "configuration": config_names(manifest),
                "requires": requires,
                "llm": {
                    "mode": str(llm.get("mode", "unspecified")).strip() or "unspecified",
                    "deterministicFallback": str(llm.get("deterministicFallback", "")).strip(),
                },
                "capabilities": sorted(capabilities, key=lambda item: item["name"].lower()),
            }
        )

    model = {
        "schemaVersion": 1,
        "generatedBy": f"mongoose {MONGOOSE_VERSION}",
        "source": {
            "root": ".",
            "agentManifests": [relative_posix(path, root) for path in manifests],
            "runtimeContractVersion": SUPPORTED_RUNTIME_CONTRACT_VERSION,
            "manifestSchemaVersion": SUPPORTED_MANIFEST_SCHEMA_VERSION,
        },
        "runtime": {
            "name": "Mongoose Runtime",
            "responsibilities": [
                "install agent commands",
                "validate manifests",
                "discover capabilities",
                "route requests",
                "provide runtime context",
                "manage provider profiles",
            ],
        },
        "providers": [
            {"name": "configuration", "status": "implemented", "interface": "environment and user-local config names"},
            {"name": "logs", "status": "implemented", "interface": "redacted JSONL logs"},
            {"name": "state", "status": "implemented", "interface": "user-local state directories"},
            {"name": "storage", "status": "implemented", "interface": "agent-scoped local storage path"},
            {"name": "llm", "status": "profile-management", "interface": "provider-neutral LLM profiles and ping"},
            {"name": "memory", "status": "implemented", "interface": "redacted local JSONL memory records"},
            {"name": "tools", "status": "planned", "interface": "runtime provider descriptor"},
            {"name": "apiProfiles", "status": "planned", "interface": "configured external API profiles"},
        ],
        "externalSystems": [{"name": "YNAB API", "access": "read-only", "usedByTaskType": "ynab"}],
        "agents": sorted(agents, key=lambda item: item["commandName"].lower()),
    }
    return model


def render_architecture_model_json(model: dict[str, Any]) -> str:
    return json.dumps(model, indent=2, sort_keys=True) + "\n"


def render_agents_sysml(model: dict[str, Any]) -> str:
    lines = [
        "// Generated by `mongoose architecture generate`. Do not edit by hand.",
        "package MongooseAgents {",
        "  part def MongooseRuntime;",
        "  part def Agent;",
        "  part def Capability;",
        "  part runtime : MongooseRuntime;",
        "",
    ]
    for agent in model["agents"]:
        agent_id = agent["id"]
        lines.extend(
            [
                f"  part {agent_id} : Agent {{",
                f'    attribute commandName = "{sysml_string(agent["commandName"])}";',
                f'    attribute displayName = "{sysml_string(agent["displayName"])}";',
                f'    attribute manifestPath = "{sysml_string(agent["manifestPath"])}";',
                f'    attribute entrypointPath = "{sysml_string(agent["entrypointPath"])}";',
                f'    attribute llmMode = "{sysml_string(agent["llm"]["mode"])}";',
            ]
        )
        for item in agent["taskTypes"]:
            lines.append(f'    attribute taskType = "{sysml_string(item)}";')
        for item in agent["configuration"]["required"]:
            lines.append(f'    attribute requiredConfiguration = "{sysml_string(item)}";')
        for capability in agent["capabilities"]:
            capability_id = f"{agent_id}_{capability['id']}"
            lines.extend(
                [
                    f"    part {capability_id} : Capability {{",
                    f'      attribute name = "{sysml_string(capability["name"])}";',
                    f'      attribute displayName = "{sysml_string(capability["displayName"])}";',
                    f'      attribute entrypointPath = "{sysml_string(capability["entrypointPath"])}";',
                    f'      attribute llmMode = "{sysml_string(capability["llm"]["mode"])}";',
                ]
            )
            for item in capability["taskTypes"]:
                lines.append(f'      attribute taskType = "{sysml_string(item)}";')
            for item in capability["configuration"]["required"]:
                lines.append(f'      attribute requiredConfiguration = "{sysml_string(item)}";')
            lines.append("    }")
        lines.append("  }")
        lines.append(f"  connect runtime to {agent_id};")
        lines.append("")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_runtime_sysml(model: dict[str, Any]) -> str:
    lines = [
        "// Generated by `mongoose architecture generate`. Do not edit by hand.",
        "package MongooseRuntimeRouting {",
        "  action def InstallAgent;",
        "  action def ValidateManifest;",
        "  action def DiscoverCapabilities;",
        "  action def RouteRequest;",
        "  action def DispatchCapability;",
        "  action def ReadExternalApi;",
        "  action runtimeRequestFlow {",
        "    first start;",
        "    then validateManifest : ValidateManifest;",
        "    then discoverCapabilities : DiscoverCapabilities;",
        "    then routeRequest : RouteRequest;",
        "",
    ]
    for agent in model["agents"]:
        for capability in agent["capabilities"]:
            branch_name = normalize_architecture_id(
                f"{agent['commandName']}_{capability['name']}", "RouteBranch"
            )
            lines.extend(
                [
                    f"    then {branch_name} : DispatchCapability;",
                    f'    // branch taskTypes: {", ".join(capability["taskTypes"]) or "unspecified"}',
                ]
            )
            if "ynab" in capability["taskTypes"] or "YNAB_ACCESS_TOKEN" in capability["configuration"]["required"]:
                lines.append(f"    then {branch_name}_ReadYNAB : ReadExternalApi;")
        lines.append("")
    lines.extend(
        [
            "    then done;",
            "  }",
            "}",
        ]
    )
    return "\n".join(lines) + "\n"


def render_agents_mermaid(model: dict[str, Any]) -> str:
    lines = [
        "%% Generated by `mongoose architecture generate`. Do not edit by hand.",
        "flowchart LR",
        '  runtime["Mongoose Runtime"]',
    ]
    for agent in model["agents"]:
        agent_node = mermaid_id(f"agent_{agent['commandName']}", "agent")
        lines.append(f'  {agent_node}["{mermaid_label(agent["displayName"])}"]')
        lines.append(f"  runtime --> {agent_node}")
        for capability in agent["capabilities"]:
            capability_node = mermaid_id(f"{agent_node}_{capability['name']}", "capability")
            lines.append(f'  {capability_node}["{mermaid_label(capability["displayName"])}"]')
            lines.append(f"  {agent_node} --> {capability_node}")
    return "\n".join(lines) + "\n"


def render_runtime_mermaid(model: dict[str, Any]) -> str:
    lines = [
        "%% Generated by `mongoose architecture generate`. Do not edit by hand.",
        "flowchart TD",
        '  request["User request"] --> route["mongoose route"]',
        '  route --> manifest["Installed manifest metadata"]',
        '  manifest --> select["Select capability"]',
    ]
    for agent in model["agents"]:
        for capability in agent["capabilities"]:
            capability_node = mermaid_id(f"dispatch_{agent['commandName']}_{capability['name']}", "dispatch")
            task_label = ", ".join(capability["taskTypes"]) or capability["name"]
            lines.append(f'  select -->|"{mermaid_label(task_label)}"| {capability_node}["{mermaid_label(agent["commandName"])} {mermaid_label(capability["name"])}"]')
            if "ynab" in capability["taskTypes"] or "YNAB_ACCESS_TOKEN" in capability["configuration"]["required"]:
                lines.append(f'  {capability_node} --> ynab["YNAB API read-only"]')
            else:
                lines.append(f'  {capability_node} --> local["Local deterministic execution"]')
    return "\n".join(lines) + "\n"


def render_providers_mermaid(model: dict[str, Any]) -> str:
    lines = [
        "%% Generated by `mongoose architecture generate`. Do not edit by hand.",
        "flowchart LR",
        '  runtime["Mongoose Runtime"]',
    ]
    for provider in model["providers"]:
        provider_node = mermaid_id(f"provider_{provider['name']}", "provider")
        label = f"{provider['name']} ({provider['status']})"
        lines.append(f'  runtime --> {provider_node}["{mermaid_label(label)}"]')
    for external in model["externalSystems"]:
        external_node = mermaid_id(f"external_{external['name']}", "external")
        lines.append(f'  runtime -.-> {external_node}["{mermaid_label(external["name"])}"]')
    return "\n".join(lines) + "\n"


def architecture_outputs(root: Path, output_root: str | None = None) -> dict[Path, str]:
    model = build_architecture_model(root)
    paths = architecture_output_paths(root, output_root)
    return {
        paths["model"]: render_architecture_model_json(model),
        paths["agents_sysml"]: render_agents_sysml(model),
        paths["runtime_sysml"]: render_runtime_sysml(model),
        paths["agents_mermaid"]: render_agents_mermaid(model),
        paths["runtime_mermaid"]: render_runtime_mermaid(model),
        paths["providers_mermaid"]: render_providers_mermaid(model),
    }


def write_architecture_outputs(root: Path, output_root: str | None = None) -> list[Path]:
    outputs = architecture_outputs(root, output_root)
    for path, content in outputs.items():
        atomic_write_text(path, content)
    return sorted(outputs)


def validate_architecture_outputs(root: Path, output_root: str | None = None) -> list[Path]:
    stale: list[Path] = []
    outputs = architecture_outputs(root, output_root)
    for path, expected in outputs.items():
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            stale.append(path)
    return sorted(stale)


def cmd_architecture_generate(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    written = write_architecture_outputs(root, args.output_root)
    print_success("Generated Mongoose architecture artifacts.")
    for path in written:
        print(f"  {relative_posix(path, root) if path.is_relative_to(root) else path}")
    return 0


def cmd_architecture_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    stale = validate_architecture_outputs(root, args.output_root)
    if stale:
        print_error("Architecture artifacts are stale or missing.")
        for path in stale:
            print(f"  {relative_posix(path, root) if path.is_relative_to(root) else path}")
        print_muted("Regenerate with: mongoose architecture generate --root .")
        return 1
    print_success("Architecture artifacts are fresh.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    examples = """examples:
  mongoose --version
  mongoose setup
  mongoose list
  mongoose list --installed
  mongoose capabilities
  mongoose install Njord
  mongoose install C:\\path\\to\\agent
  mongoose show Njord
  mongoose run Njord config status
  mongoose route --task-type budget-summary "current budget"
  mongoose jobs list
  mongoose status
  mongoose llm setup
  mongoose llm setup --provider ollama --yes --bootstrap
  mongoose llm add openai-main --provider openai --model gpt-4.1-mini --api-key-env OPENAI_API_KEY
  mongoose llm ping openai-main
  mongoose validate
  mongoose architecture generate --root .
  mongoose architecture validate --root .
  mongoose remove Njord
  mongoose update
  mongoose update --registry-only
  mongoose update --self-only
  mongoose state --init
  mongoose setup --registry-root C:\\path\\to\\Agents

quick start:
  1. Run `mongoose setup` from the Mongoose checkout.
  2. Run `mongoose install Njord` to install the first agent.
  3. Run `mongoose llm setup` before using LLM-backed agent features.
  4. Run `mongoose run Njord` to start Njord.

workflow:
  1. Run `mongoose setup` to configure the local registry checkout.
  2. Run `mongoose list` to see available agents.
  3. Run `mongoose install <agent-or-path>` to install one as a command.
  4. Run `mongoose show <agent>` to inspect installed metadata and capabilities.
  5. Run `mongoose capabilities` to inspect routeable installed capabilities.
  6. Run `mongoose route --task-type <type> ...` or `mongoose run <agent> ...`.
  7. Run `mongoose jobs list` and `mongoose status` to inspect runtime activity.
  8. Run `mongoose llm setup` before enabling LLM-backed agents.
  9. Run `mongoose update` to refresh the registry and check for a Mongoose CLI update.
  10. Use `mongoose update --registry-only` or `mongoose update --self-only` for scoped updates.
"""
    parser = argparse.ArgumentParser(
        prog="mongoose",
        description="Install, inspect, run, remove, and update local agents.",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=version_string(),
        help="Print the Mongoose CLI version.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color in human-readable output.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser(
        "setup",
        help="Configure mongoose for an agent registry.",
        description="Configure mongoose with a local registry checkout and optional GitHub registry URL.",
    )
    setup.add_argument("--registry-root", default=".", help="Local registry checkout path. Defaults to the current directory.")
    setup.add_argument("--registry-url", default=DEFAULT_REGISTRY_URL, help="Git registry URL.")
    setup.set_defaults(handler=cmd_setup)

    state = subparsers.add_parser(
        "state",
        help="Show or initialize local Mongoose state paths.",
        description="Show the shared user-local state, config, job, and log paths used by Mongoose.",
    )
    state.add_argument("--init", action="store_true", help="Create the local state directory layout.")
    state.add_argument("--json", action="store_true", help="Print paths as JSON.")
    state.add_argument(
        "--cleanup-logs",
        action="store_true",
        help="Remove JSONL log files older than the retention period.",
    )
    state.add_argument(
        "--log-retention-days",
        type=int,
        default=DEFAULT_LOG_RETENTION_DAYS,
        help="Number of days of logs to keep when --cleanup-logs is used.",
    )
    state.set_defaults(handler=cmd_state)

    status = subparsers.add_parser(
        "status",
        help="Show Mongoose runtime health and observability summary.",
        description="Summarize installed agents, registry health, jobs, runtime state, and LLM profile setup.",
    )
    status.add_argument("--json", action="store_true", help="Print status as JSON.")
    status.set_defaults(handler=cmd_status)

    runtime = subparsers.add_parser(
        "runtime",
        help="Inspect and control the local Mongoose runtime foundation.",
        description="Show or mark local runtime foundation state. Background daemon scheduling is future work.",
    )
    runtime_subparsers = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_status = runtime_subparsers.add_parser("status", help="Show runtime status and health.")
    runtime_status.add_argument("--json", action="store_true", help="Print runtime status as JSON.")
    runtime_status.set_defaults(handler=cmd_runtime_status)
    runtime_start = runtime_subparsers.add_parser("start", help="Mark runtime foundation as running.")
    runtime_start.set_defaults(handler=cmd_runtime_start)
    runtime_stop = runtime_subparsers.add_parser("stop", help="Mark runtime foundation as stopped.")
    runtime_stop.set_defaults(handler=cmd_runtime_stop)
    runtime_restart = runtime_subparsers.add_parser("restart", help="Restart the runtime foundation marker.")
    runtime_restart.set_defaults(handler=cmd_runtime_restart)

    jobs = subparsers.add_parser(
        "jobs",
        help="Inspect recent Mongoose agent jobs and run records.",
        description="List, show, and request cancellation for jobs created by mongoose run and route.",
    )
    jobs_subparsers = jobs.add_subparsers(dest="jobs_command", required=True)
    jobs_list = jobs_subparsers.add_parser("list", aliases=["ls"], help="List recent jobs.")
    jobs_list.add_argument("--limit", type=int, default=20, help="Maximum jobs to show.")
    jobs_list.add_argument("--json", action="store_true", help="Print jobs as JSON.")
    jobs_list.set_defaults(handler=cmd_jobs_list)
    jobs_show = jobs_subparsers.add_parser("show", help="Show one job record.")
    jobs_show.add_argument("id", help="Job id to inspect.")
    jobs_show.add_argument("--json", action="store_true", help="Print job as JSON.")
    jobs_show.set_defaults(handler=cmd_jobs_show)
    jobs_cancel = jobs_subparsers.add_parser("cancel", help="Request cancellation for an active job.")
    jobs_cancel.add_argument("id", help="Job id to cancel.")
    jobs_cancel.set_defaults(handler=cmd_jobs_cancel)

    memory = subparsers.add_parser(
        "memory",
        help="Append and inspect local shared memory records.",
        description="Store and query redacted local memory records used by loop-aware capabilities.",
    )
    memory_subparsers = memory.add_subparsers(dest="memory_command", required=True)
    memory_append = memory_subparsers.add_parser(
        "append",
        help="Append one memory record from JSON.",
        description="Append one redacted memory record from --record-json, --record-file, or stdin.",
    )
    memory_append.add_argument("--record-json", help="Memory record JSON object.")
    memory_append.add_argument("--record-file", help="Path to a JSON file containing one memory record object.")
    memory_append.add_argument("--json", action="store_true", help="Print the stored record as JSON.")
    memory_append.set_defaults(handler=cmd_memory_append)

    memory_list = memory_subparsers.add_parser(
        "list",
        aliases=["ls"],
        help="List stored memory records.",
    )
    memory_list.add_argument("--limit", type=int, default=20, help="Maximum records to show; use 0 for all.")
    memory_list.add_argument("--agent", help="Filter by agentId.")
    memory_list.add_argument("--capability", help="Filter by capabilityId.")
    memory_list.add_argument("--record-type", help="Filter by recordType.")
    memory_list.add_argument("--status", help="Filter by top-level, loop, outcome, or user decision status.")
    memory_list.add_argument("--outcome", help="Filter by outcome status, summary, or result text.")
    memory_list.add_argument("--from", dest="from_date", help="Filter records created at or after this ISO timestamp.")
    memory_list.add_argument("--to", dest="to_date", help="Filter records created at or before this ISO timestamp.")
    memory_list.add_argument("--min-confidence", type=float, help="Filter records below this confidence value.")
    memory_list.add_argument("--subject", help="Case-insensitive text search across the stored record.")
    memory_list.add_argument("--json", action="store_true", help="Print matching records as JSON.")
    memory_list.set_defaults(handler=cmd_memory_list)

    memory_context = memory_subparsers.add_parser(
        "context",
        help="Build compact prompt context from memory records.",
        description="Return prompt-ready memory summaries with provenance, redaction, and informational-only guardrails.",
    )
    memory_context.add_argument("--limit", type=int, default=8, help="Maximum context records to include; use 0 for all.")
    memory_context.add_argument("--agent", help="Filter by agentId.")
    memory_context.add_argument("--capability", help="Filter by capabilityId.")
    memory_context.add_argument("--record-type", help="Filter by recordType.")
    memory_context.add_argument("--status", help="Filter by top-level, loop, outcome, or user decision status.")
    memory_context.add_argument("--outcome", help="Filter by outcome status, summary, or result text.")
    memory_context.add_argument("--from", dest="from_date", help="Filter records created at or after this ISO timestamp.")
    memory_context.add_argument("--to", dest="to_date", help="Filter records created at or before this ISO timestamp.")
    memory_context.add_argument("--min-confidence", type=float, help="Filter records below this confidence value.")
    memory_context.add_argument("--subject", help="Case-insensitive text search across the stored record.")
    memory_context.add_argument("--json", action="store_true", help="Print prompt context as JSON.")
    memory_context.set_defaults(handler=cmd_memory_context)

    memory_show = memory_subparsers.add_parser(
        "show",
        help="Show one memory record.",
    )
    memory_show.add_argument("record_id", help="Memory record id to inspect.")
    memory_show.add_argument("--json", action="store_true", help="Print the record as JSON.")
    memory_show.set_defaults(handler=cmd_memory_show)

    list_parser = subparsers.add_parser(
        "list",
        aliases=["ls"],
        help="List available or installed agents.",
        description="List installable agents discovered from agents/*/agent.json and installed local state.",
    )
    list_parser.add_argument(
        "--installed",
        action="store_true",
        help="Only list agents installed into local Mongoose state.",
    )
    list_parser.set_defaults(handler=cmd_list)

    capabilities = subparsers.add_parser(
        "capabilities",
        aliases=["caps"],
        help="List installed routeable capabilities.",
        description="List capability metadata from installed agent manifests for Mongoose routing.",
    )
    capabilities.set_defaults(handler=cmd_capabilities)

    install = subparsers.add_parser(
        "install",
        help="Install an agent as a user-local command.",
        description="Install an agent command into the user-local Agents bin directory from a registry name or local agent path.",
    )
    install.add_argument("agent", help="Agent commandName or local agent path to install, such as Njord.")
    install.set_defaults(handler=cmd_install)

    uninstall = subparsers.add_parser(
        "uninstall",
        aliases=["remove", "rm"],
        help="Uninstall a user-local agent command.",
        description="Remove an installed agent command and local Mongoose install state.",
    )
    uninstall.add_argument("agent", help="Agent commandName to remove, such as Njord.")
    uninstall.set_defaults(handler=cmd_uninstall)

    show = subparsers.add_parser(
        "show",
        help="Show installed agent metadata and capabilities.",
        description="Show manifest, entrypoint, source, launcher, and capability metadata for an agent.",
    )
    show.add_argument("agent", help="Agent commandName to inspect, such as Njord.")
    show.set_defaults(handler=cmd_show)

    run_parser = subparsers.add_parser(
        "run",
        help="Run an installed agent entrypoint.",
        description="Dispatch arguments to an installed agent entrypoint through Mongoose.",
    )
    run_parser.add_argument("agent", help="Installed agent commandName to run, such as Njord.")
    run_parser.add_argument(
        "agent_args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to the agent entrypoint.",
    )
    run_parser.set_defaults(handler=cmd_run)

    route = subparsers.add_parser(
        "route",
        help="Route a request to an installed agent capability.",
        description="Select an installed agent capability by task type or request text, then dispatch to it.",
    )
    route.add_argument(
        "--task-type",
        help="Direct task classification hint, such as budget-summary or finance.",
    )
    route.add_argument("--agent", help="Restrict routing to one installed agent commandName.")
    route.add_argument("--capability", help="Restrict routing to one capability name.")
    route.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the selected capability and invocation without running it.",
    )
    route.add_argument(
        "request",
        nargs=argparse.REMAINDER,
        help="Request words to pass to the selected capability.",
    )
    route.set_defaults(handler=cmd_route)

    llm_examples = """recommended setup:
  mongoose llm setup
  mongoose llm setup --provider ollama --yes
  mongoose llm setup --provider ollama --yes --bootstrap
  mongoose llm ping
  mongoose llm invoke "Reply with only: ready"

advanced manual setup:
  mongoose llm add openai-main --provider openai --model gpt-4.1-mini --api-key-env OPENAI_API_KEY --default
"""
    llm = subparsers.add_parser(
        "llm",
        help="Configure and test provider-neutral LLM profiles.",
        description="Configure, inspect, select, ping, and invoke secret-safe provider-neutral LLM profiles. Start with `mongoose llm setup`; use `llm add` for advanced manual setup.",
        epilog=llm_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    llm_subparsers = llm.add_subparsers(dest="llm_command", required=True)

    llm_setup = llm_subparsers.add_parser(
        "setup",
        help="Walk through guided LLM profile setup.",
        description="Configure a provider-neutral LLM profile with prompts and secret-safe diagnostics.",
    )
    llm_setup.add_argument("--provider", choices=["ollama", "local-http", "openai", "anthropic", "fake"], help="Provider setup path.")
    llm_setup.add_argument("--name", help="Profile name.")
    llm_setup.add_argument("--model", help="Model name.")
    llm_setup.add_argument("--endpoint", help="Endpoint URL for local HTTP providers.")
    llm_setup.add_argument("--api-key-env", help="Environment variable that contains a remote provider API key.")
    llm_setup.add_argument("--default", action="store_true", help="Make this profile the default.")
    llm_setup.add_argument("--yes", action="store_true", help="Accept non-secret defaults for omitted prompts.")
    llm_setup.add_argument("--skip-ping", action="store_true", help="Configure the profile without pinging it.")
    llm_setup.add_argument("--bootstrap", action="store_true", help="For Ollama, install/check Ollama, pull the model, configure the profile, and verify invocation.")
    llm_setup.add_argument("--timeout", type=float, help="Override ping and warmup timeout in seconds.")
    llm_setup.set_defaults(handler=cmd_llm_setup)

    llm_add = llm_subparsers.add_parser(
        "add",
        aliases=["configure"],
        help="Add or update an LLM provider profile.",
        description="Store a provider-neutral LLM profile with secret references only.",
    )
    llm_add.add_argument("name", help="Profile name, such as openai-main.")
    llm_add.add_argument("--provider", required=True, choices=sorted(LLM_PROVIDERS), help="Provider backend type.")
    llm_add.add_argument("--model", required=True, help="Model name for this profile.")
    llm_add.add_argument("--api-key-env", help="Environment variable that contains the API key or token.")
    llm_add.add_argument("--endpoint", help="Optional provider endpoint URL.")
    llm_add.add_argument("--capability", action="append", help="Optional provider capability label; may be repeated.")
    llm_add.add_argument("--default", action="store_true", help="Select this profile as the default.")
    llm_add.set_defaults(handler=cmd_llm_add)

    llm_list = llm_subparsers.add_parser(
        "list",
        aliases=["ls"],
        help="List configured LLM profiles without printing secrets.",
    )
    llm_list.set_defaults(handler=cmd_llm_list)

    llm_use = llm_subparsers.add_parser(
        "use",
        help="Select the default LLM profile.",
    )
    llm_use.add_argument("name", help="Configured profile name to use by default.")
    llm_use.set_defaults(handler=cmd_llm_use)

    llm_show = llm_subparsers.add_parser(
        "show",
        help="Show non-secret LLM profile metadata.",
    )
    llm_show.add_argument("name", nargs="?", help="Profile name; defaults to the active default profile.")
    llm_show.set_defaults(handler=cmd_llm_show)

    llm_ping = llm_subparsers.add_parser(
        "ping",
        help="Test a configured LLM profile without printing secrets.",
    )
    llm_ping.add_argument("name", nargs="?", help="Profile name; defaults to the active default profile.")
    llm_ping.add_argument("--timeout", type=float, help="Override ping timeout in seconds.")
    llm_ping.set_defaults(handler=cmd_llm_ping)

    llm_invoke = llm_subparsers.add_parser(
        "invoke",
        help="Invoke a configured LLM profile.",
        description="Invoke a configured provider-neutral LLM profile.",
    )
    llm_invoke.add_argument("prompt", nargs="*", help="Prompt text. Reads stdin when omitted.")
    llm_invoke.add_argument("--profile", help="Profile name; defaults to the active default profile.")
    llm_invoke.add_argument("--system", help="Optional system prompt.")
    llm_invoke.add_argument("--timeout", type=float, help="Override invocation timeout in seconds.")
    llm_invoke.add_argument("--json", action="store_true", help="Print structured invocation result JSON.")
    llm_invoke.set_defaults(handler=cmd_llm_invoke)

    validate = subparsers.add_parser(
        "validate",
        help="Validate agent manifest metadata.",
        description="Validate one agent manifest, one agent directory, or all manifests in the configured registry.",
    )
    validate.add_argument(
        "path",
        nargs="?",
        help="Optional manifest, agent directory, or registry root path to validate.",
    )
    validate.set_defaults(handler=cmd_validate)

    architecture = subparsers.add_parser(
        "architecture",
        aliases=["arch"],
        help="Generate and validate Mongoose architecture docs.",
        description=(
            "Generate or validate deterministic architecture artifacts from agent manifests, "
            "including the shared model, SysML v2 text, and Mermaid diagrams."
        ),
    )
    architecture_subparsers = architecture.add_subparsers(dest="architecture_command", required=True)

    architecture_generate = architecture_subparsers.add_parser(
        "generate",
        help="Generate architecture model, SysML, and Mermaid artifacts.",
    )
    architecture_generate.add_argument(
        "--root",
        default=".",
        help="Repository root to scan for agents/*/agent.json.",
    )
    architecture_generate.add_argument(
        "--output-root",
        help="Optional output directory; defaults to <root>/docs/architecture.",
    )
    architecture_generate.set_defaults(handler=cmd_architecture_generate)

    architecture_validate = architecture_subparsers.add_parser(
        "validate",
        help="Validate generated architecture artifacts are fresh.",
    )
    architecture_validate.add_argument(
        "--root",
        default=".",
        help="Repository root to scan for agents/*/agent.json.",
    )
    architecture_validate.add_argument(
        "--output-root",
        help="Optional output directory; defaults to <root>/docs/architecture.",
    )
    architecture_validate.set_defaults(handler=cmd_architecture_validate)

    update = subparsers.add_parser(
        "update",
        help="Update the agent registry and installed Mongoose CLI.",
        description=(
            "Refresh the configured Git-backed registry and check the installed Mongoose CLI "
            "against GitHub Releases. Use scope flags for automation and recovery workflows."
        ),
    )
    update_scope = update.add_mutually_exclusive_group()
    update_scope.add_argument(
        "--registry-only",
        action="store_true",
        help="Only update the configured agent registry; do not check or replace the Mongoose CLI.",
    )
    update_scope.add_argument(
        "--self",
        "--self-only",
        action="store_true",
        dest="self_only",
        help="Only update the installed Mongoose CLI from the latest stable GitHub Release.",
    )
    update.add_argument(
        "--include-prerelease",
        action="store_true",
        help="Allow prerelease GitHub Releases when checking the Mongoose CLI update phase.",
    )
    update.set_defaults(handler=cmd_update)

    return parser


def version_string() -> str:
    if MONGOOSE_RELEASE_KIND == "official":
        tag_suffix = f", {MONGOOSE_RELEASE_TAG}" if MONGOOSE_RELEASE_TAG else ""
        return f"mongoose {MONGOOSE_VERSION} (official release{tag_suffix})"
    return f"mongoose {MONGOOSE_VERSION} (development)"


def main() -> int:
    configure_output()
    parser = build_parser()
    args = parser.parse_args()
    set_output_color(should_use_color(getattr(args, "no_color", False)))
    try:
        return args.handler(args)
    except ValueError as exc:
        print_error(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

