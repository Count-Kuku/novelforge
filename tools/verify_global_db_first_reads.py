from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_utils import isolated_workspace, retry_unlink


def _safe_unlink(workspace: Path, file: Path) -> bool:
    return retry_unlink(workspace, file)


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def main() -> int:
    previous_flag = os.environ.get("NOVELFORGE_WRITE_JSON_MIRRORS")
    os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "1"
    try:
        with isolated_workspace("novelforge_global_db_verify_") as workspace:
            from memory import (
                GLOBAL_PROMPT_OPTIONS_PATH,
                GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH,
                GLOBAL_RULES_PATH,
                LLM_PROFILES_PATH,
                inspect_global_database,
                load_global_prompt_options,
                load_global_rules,
                load_llm_profiles,
                load_rule_conflict_resolutions,
                save_global_prompt_options,
                save_global_rules,
                save_llm_profiles,
                save_rule_conflict_resolutions,
            )

            save_llm_profiles({
                "active_profile_id": "global_verify_profile",
                "profiles": [{
                    "id": "global_verify_profile",
                    "name": "Global Verify Profile",
                    "base_url": "https://example.test",
                    "api_key": "verify-key",
                    "model_name": "verify-model",
                    "embedding_model_name": "verify-embedding",
                }],
            })
            save_global_rules({"write": ["global write rule"], "review": ["global review rule"]})
            save_global_prompt_options([{
                "id": "global_prompt_verify",
                "name": "Global Prompt Verify",
                "capability": "write",
                "category": "custom",
                "slot": "custom",
                "content": "global prompt",
                "enabled": True,
            }])
            save_rule_conflict_resolutions("_global_verify_project", "global", [{
                "id": "global_conflict_verify",
                "scope": "write",
                "title": "Global Conflict Verify",
                "decision": "global conflict decision",
            }])

            mirrors = [
                LLM_PROFILES_PATH,
                GLOBAL_RULES_PATH,
                GLOBAL_PROMPT_OPTIONS_PATH,
                GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH,
            ]
            deleted = []
            for file in mirrors:
                if _safe_unlink(workspace, file):
                    deleted.append(str(file.resolve().relative_to(workspace.resolve())))

            failures: list[str] = []
            _expect(load_llm_profiles().get("active_profile_id") == "global_verify_profile", "llm_profiles", failures)
            _expect(load_global_rules().get("write") == ["global write rule"], "global_rules", failures)
            _expect(load_global_prompt_options()[0].get("id") == "global_prompt_verify", "global_prompt_options", failures)
            _expect(load_rule_conflict_resolutions("_global_verify_project", "global")[0].get("decision") == "global conflict decision", "global_rule_conflicts", failures)

            health = inspect_global_database()
            result = {
                "ok": not failures and health.get("ok"),
                "workspace": str(workspace),
                "deleted_json_mirrors": deleted,
                "failures": failures,
                "health": health,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ok"] else 1
    finally:
        if previous_flag is None:
            os.environ.pop("NOVELFORGE_WRITE_JSON_MIRRORS", None)
        else:
            os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = previous_flag


if __name__ == "__main__":
    raise SystemExit(main())
