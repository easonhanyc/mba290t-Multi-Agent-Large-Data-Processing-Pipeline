"""Load config/pipeline.toml and derive the version strings that key every cache."""

import copy
import tomllib
from pathlib import Path

from . import labels, segment
from .util import PROJECT_ROOT, sha256_file, short_hash

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "pipeline.toml"
STUB_PREFIX = "stub-"
CLASSIFIER_BACKENDS = ("jev", "decisions")  # typed-question classifiers: one review per request
BACKENDS = ("llm", "hybrid") + CLASSIFIER_BACKENDS  # hybrid = batched LLM labels + Decisions cross-check per text


class ConfigError(ValueError):
    pass


def project_path(value) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else PROJECT_ROOT / p


# Settings that change price or latency but never an answer: excluded from label_config / stage_config,
# so switching Flex <-> Standard or a timeout keeps valid saved results reusable.
COST_ONLY_KEYS = ("service_tier", "timeout_s", "backlog_max")


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
            if e["backend"] in CLASSIFIER_BACKENDS:
                j = e[e["backend"]]
                return {"provider": j["provider"], "model": j["model"], "effort": "n/a"}
            l = e["llm"]
            return {"provider": l["provider"], "model": l["model"], "effort": l["effort"]}
        if role == "crosscheck":
            c = e["crosscheck"]
            return {"provider": c["provider"], "model": c["model"], "effort": "n/a",
                    "enabled": e["backend"] == "hybrid", "fields": list(c["fields"])}
        if role in ("fallback1", "fallback2"):
            f = e[role]
            return {"provider": f["provider"], "model": f["model"], "effort": f["effort"],
                    "enabled": bool(f.get("enabled", True)), "max_fraction": float(f["max_fraction"])}
        s = self.data[role]
        return {"provider": s["provider"], "model": s["model"], "effort": s["effort"]}

    def active_providers(self, stages=None) -> list:
        """Providers the run can call; with `stages`, only those the requested stages use."""
        want = lambda st: stages is None or st in stages
        names = []
        if want("enrich"):
            names.append(self.role_settings("enrich_primary")["provider"])
            if self.role_settings("crosscheck")["enabled"]:
                names.append(self.role_settings("crosscheck")["provider"])
            for fb in ("fallback1", "fallback2"):
                r = self.role_settings(fb)
                if r["enabled"] and r["max_fraction"] > 0:
                    names.append(r["provider"])
        names += [self.role_settings(r)["provider"] for r in ("verify", "group", "memo") if want(r)]
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
        cls = e["backend"] if e["backend"] in CLASSIFIER_BACKENDS else None
        p = self.role_settings("enrich_primary")
        parts = [f"{p['model']}[{e['backend']}]" if cls else f"{p['model']}@{p['effort']}"]
        hybrid = e["backend"] == "hybrid"
        if hybrid:
            c = self.role_settings("crosscheck")
            parts[0] += f"+{c['model']}[decisions:{','.join(c['fields'])}]"
        for fb in ("fallback1", "fallback2"):
            r = self.role_settings(fb)
            if r["enabled"] and r["max_fraction"] > 0:
                parts.append(f"{r['model']}@{r['effort']}({r['max_fraction'] * 100:g}%)")
        affecting = {
            "backend": e["backend"],
            "classifier": e[cls] if cls else None,
            "llm": _label_affecting(e["llm"]),
            "fallback1": _label_affecting(e["fallback1"]), "fallback2": _label_affecting(e["fallback2"]),
            "llm_batch_size": e["llm_batch_size"] if e["backend"] in ("llm", "hybrid") else None,
            "crosscheck": _label_affecting(e["crosscheck"]) if hybrid else None,
            "crosscheck_questions_sha": self._file_hash(e["crosscheck"]["questions"]) if hybrid else None,
            "questions_sha": self._file_hash(e[cls]["questions"]) if cls else None,
            "llm_prompt_sha": self._file_hash(e["llm"]["prompt"]),
            "versions": [labels.TAXONOMY_VERSION, segment.SEGMENTER_VERSION, labels.ENTITY_LEXICON_VERSION],
        }
        return f"{'>'.join(parts)}|{e['prompt_version']}|{e['schema_version']}|cfg-{short_hash(affecting)}"

    def stage_config(self, stage: str) -> str:
        """Cache/provenance key of a model stage: '<model alias>@<effort>|<stage>-v1|cfg-<hash>'.

        '<stage>-v1' is the version of this key format, not of the prompt file: the prompt is identified by the SHA-256
        of its contents inside cfg-<hash> (so verify-v1 uses prompts/verify_v2.md and memo-v1 prompts/memo_v2.md), and
        renaming the label would change every saved cache key. The exact model ID the provider reported is in each call's
        model_reported field (calls.jsonl, state.sqlite), next to the configured alias.
        """
        if f"stage:{stage}" in self.pinned:
            return self.pinned[f"stage:{stage}"]
        s = self.data[stage]
        affecting = _label_affecting(s)
        affecting["prompt_sha"] = self._file_hash(s["prompt"])
        return f"{s['model']}@{s['effort']}|{stage}-v1|cfg-{short_hash(affecting)}"

    def _validate(self):
        e = self.data.get("enrich", {})
        if e.get("backend") not in BACKENDS:
            raise ConfigError(f"enrich.backend must be one of {BACKENDS}")
        if e.get("backend") == "hybrid":
            bad = set(e["crosscheck"]["fields"]) - {"issue", "intent", "severity"}
            if bad or not e["crosscheck"]["fields"]:
                raise ConfigError(f"enrich.crosscheck.fields must be a non-empty subset of issue/intent/severity, not {bad}")
        if not 1 <= int(e.get("llm_batch_size", 1)) <= 50:
            raise ConfigError("enrich.llm_batch_size must be between 1 and 50 (contract limit)")
        if int(self.data["run"]["workers"]) < 1:
            raise ConfigError("run.workers must be >= 1")
        for fb in ("fallback1", "fallback2"):
            frac = float(e[fb]["max_fraction"])
            if not 0 <= frac <= 1:
                raise ConfigError(f"enrich.{fb}.max_fraction must be within [0, 1]")
        for role in ("enrich_primary", "crosscheck", "fallback1", "fallback2", "verify", "group", "memo"):
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
        for node in (e["jev"], e["decisions"], e["crosscheck"], e["llm"], e["fallback1"], e["fallback2"], data["verify"], data["group"], data["memo"]):
            if not node["model"].startswith(STUB_PREFIX):
                node["model"] = STUB_PREFIX + node["model"]
    return Config(data, path, offline_stub=offline_stub)
