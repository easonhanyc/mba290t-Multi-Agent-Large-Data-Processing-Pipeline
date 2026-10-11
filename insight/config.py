"""Load config/pipeline.toml and derive the version strings that key every cache."""

import copy
import tomllib
from pathlib import Path

from . import labels, segment
from .util import PROJECT_ROOT, sha256_file, short_hash

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "pipeline.toml"
STUB_PREFIX = "stub-"


class ConfigError(ValueError):
    pass


def project_path(value) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else PROJECT_ROOT / p


# Settings that change price or latency but never an answer: excluded from label_config / stage_config,
# so switching Flex <-> Standard or a timeout keeps valid saved results reusable.
COST_ONLY_KEYS = ("service_tier", "timeout_s")


def _label_affecting(section: dict) -> dict:
    return {k: v for k, v in section.items() if k not in COST_ONLY_KEYS}


class Config:
    def __init__(self, data: dict, source: Path, offline_stub: bool = False):
        self.data = data
        self.source = source
        self.offline_stub = offline_stub
        self.pinned = {}  # label/stage configs read back from a run directory (read-only commands)
        self._validate()

    def pin(self, label_config=None, stage_configs=None):
        """Use the configuration strings saved by the run, so later prompt/config edits cannot orphan its results."""
        if label_config:
            self.pinned["label_config"] = label_config
        for stage, value in (stage_configs or {}).items():
            self.pinned[f"stage:{stage}"] = value

    # ---- raw access -------------------------------------------------------------------
    def __getitem__(self, key):
        return self.data[key]

    def section(self, *keys) -> dict:
        node = self.data
        for k in keys:
            node = node[k]
        return node

    # ---- derived ------------------------------------------------------------------------
    def provider(self, name: str) -> dict:
        try:
            return self.data["providers"][name]
        except KeyError:
            raise ConfigError(f"Unknown provider '{name}' in config") from None

    def role_settings(self, role: str) -> dict:
        """Provider/model/effort for a role: enrich_primary, fallback1, fallback2, verify, group, memo."""
        e = self.data["enrich"]
        if role == "enrich_primary":
            if e["backend"] == "jev":
                j = e["jev"]
                return {"provider": j["provider"], "model": j["model"], "effort": "n/a"}
            l = e["llm"]
            return {"provider": l["provider"], "model": l["model"], "effort": l["effort"]}
        if role in ("fallback1", "fallback2"):
            f = e[role]
            return {"provider": f["provider"], "model": f["model"], "effort": f["effort"],
                    "enabled": bool(f.get("enabled", True)), "max_fraction": float(f["max_fraction"])}
        s = self.data[role]
        return {"provider": s["provider"], "model": s["model"], "effort": s["effort"]}

    def active_providers(self) -> list:
        names = [self.role_settings("enrich_primary")["provider"]]
        for fb in ("fallback1", "fallback2"):
            r = self.role_settings(fb)
            if r["enabled"] and r["max_fraction"] > 0:
                names.append(r["provider"])
        names += [self.role_settings(r)["provider"] for r in ("verify", "group", "memo")]
        return sorted(set(names))

    def _file_hash(self, key_path) -> str:
        return sha256_file(project_path(key_path))[:16]

    def label_config(self) -> str:
        """model + prompt + schema version string written on every record and enrich call.

        One string covers the whole enrichment procedure (primary model and capped fallbacks),
        so primary and fallback calls name the same label_config as the records they produce;
        `labeled_by` on each record says which tier actually answered.
        """
        if "label_config" in self.pinned:
            return self.pinned["label_config"]
        e = self.data["enrich"]
        p = self.role_settings("enrich_primary")
        parts = [p["model"] if p["effort"] == "n/a" else f"{p['model']}@{p['effort']}"]
        for fb in ("fallback1", "fallback2"):
            r = self.role_settings(fb)
            if r["enabled"] and r["max_fraction"] > 0:
                parts.append(f"{r['model']}@{r['effort']}({r['max_fraction'] * 100:g}%)")
        affecting = {
            "backend": e["backend"],
            "jev": e["jev"] if e["backend"] == "jev" else None,
            "llm": _label_affecting(e["llm"]),
            "fallback1": _label_affecting(e["fallback1"]), "fallback2": _label_affecting(e["fallback2"]),
            "llm_batch_size": e["llm_batch_size"] if e["backend"] == "llm" else None,
            "questions_sha": self._file_hash(e["jev"]["questions"]) if e["backend"] == "jev" else None,
            "llm_prompt_sha": self._file_hash(e["llm"]["prompt"]),
            "versions": [labels.TAXONOMY_VERSION, segment.SEGMENTER_VERSION, labels.ENTITY_LEXICON_VERSION],
        }
        return f"{'>'.join(parts)}|{e['prompt_version']}|{e['schema_version']}|cfg-{short_hash(affecting)}"

    def stage_config(self, stage: str) -> str:
        if f"stage:{stage}" in self.pinned:
            return self.pinned[f"stage:{stage}"]
        s = self.data[stage]
        affecting = _label_affecting(s)
        affecting["prompt_sha"] = self._file_hash(s["prompt"])
        return f"{s['model']}@{s['effort']}|{stage}-v1|cfg-{short_hash(affecting)}"

    def _validate(self):
        e = self.data.get("enrich", {})
        if e.get("backend") not in ("jev", "llm"):
            raise ConfigError("enrich.backend must be 'jev' or 'llm'")
        if not 1 <= int(e.get("llm_batch_size", 1)) <= 50:
            raise ConfigError("enrich.llm_batch_size must be between 1 and 50 (contract limit)")
        if int(self.data["run"]["workers"]) < 1:
            raise ConfigError("run.workers must be >= 1")
        for fb in ("fallback1", "fallback2"):
            frac = float(e[fb]["max_fraction"])
            if not 0 <= frac <= 1:
                raise ConfigError(f"enrich.{fb}.max_fraction must be within [0, 1]")
        for role in ("enrich_primary", "fallback1", "fallback2", "verify", "group", "memo"):
            self.provider(self.role_settings(role)["provider"])


def load(path=None, overrides: dict | None = None, offline_stub: bool = False) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG
    with path.open("rb") as f:
        data = tomllib.load(f)
    data = copy.deepcopy(data)
    for dotted, value in (overrides or {}).items():
        node = data
        keys = dotted.split(".")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
    if offline_stub:
        # Offline stub: same code path and SDKs, but every model ID is renamed with a visible
        # "stub-" prefix so no artifact can be mistaken for a real model's output.
        e = data["enrich"]
        for node in (e["jev"], e["llm"], e["fallback1"], e["fallback2"], data["verify"], data["group"], data["memo"]):
            if not node["model"].startswith(STUB_PREFIX):
                node["model"] = STUB_PREFIX + node["model"]
    return Config(data, path, offline_stub=offline_stub)
