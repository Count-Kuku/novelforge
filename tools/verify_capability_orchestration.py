from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["NOVELFORGE_CREDENTIAL_BACKEND"] = "memory"
os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "0"

from novelforge.services.automatic_configuration import (
    copy_story_automatic_configurations,
    configure_operation_automatically,
    delete_automatic_configurations,
    load_automatic_configuration,
    list_automatic_configuration_revisions,
    rename_project_automatic_configurations,
)
from novelforge.services.capabilities import (
    CAPABILITY_CHAT,
    CAPABILITY_EMBEDDING,
    CapabilityRegistry,
    CapabilityStatus,
    negotiate_operation,
)
from novelforge.services.credentials import (
    delete_system_credential,
    resolve_system_credential,
    store_system_credential,
)
from novelforge.services.memory import load_llm_profiles, save_llm_profiles
from storage import get_schema_version, initialize_global_db, open_global_db
from storage.repositories import load_global_setting
from tools.verify_utils import isolated_workspace


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def verify_credentials() -> None:
    secret = "sk-stage5-secret-7890"
    metadata = store_system_credential(secret, purpose="test", owner_id="profile-a")
    check(metadata["last_four"] == "7890", "凭据元数据仅暴露末四位")
    check(len(metadata["fingerprint"]) == 64, "凭据指纹使用 SHA-256")
    check(resolve_system_credential(metadata["credential_ref"]) == secret, "系统凭据引用可解析")
    with open_global_db() as conn:
        raw_db = " ".join(
            str(value)
            for row in conn.execute("SELECT * FROM credential_references").fetchall()
            for value in tuple(row)
        )
    check(secret not in raw_db, "凭据元数据表不保存明文")
    check(delete_system_credential(metadata["credential_ref"]), "凭据可连同引用安全删除")

    rollback = store_system_credential(
        "sk-before-failed-update", purpose="test", owner_id="rollback"
    )
    with patch(
        "novelforge.services.credentials.upsert_credential_reference_row",
        side_effect=RuntimeError("simulated metadata failure"),
    ):
        try:
            store_system_credential(
                "sk-after-failed-update",
                purpose="test",
                owner_id="rollback",
                credential_ref=rollback["credential_ref"],
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("元数据写入失败应向调用者报告")
    check(
        resolve_system_credential(rollback["credential_ref"]) == "sk-before-failed-update",
        "凭据元数据写入失败会恢复旧密钥",
    )
    with patch(
        "novelforge.services.credentials.mark_credential_reference_deleted_row",
        side_effect=RuntimeError("simulated delete failure"),
    ):
        try:
            delete_system_credential(rollback["credential_ref"])
        except RuntimeError:
            pass
        else:
            raise AssertionError("凭据引用删除失败应向调用者报告")
    check(
        resolve_system_credential(rollback["credential_ref"]) == "sk-before-failed-update",
        "凭据引用删除失败会恢复密钥",
    )
    delete_system_credential(rollback["credential_ref"])


def verify_profile_migration() -> None:
    secret = "sk-profile-migration-4567"
    payload = {
        "active_profile_id": "secure-profile",
        "profiles": [{
            "id": "secure-profile",
            "name": "安全方案",
            "base_url": "https://example.invalid/v1",
            "api_key": secret,
            "model_name": "example-model",
            "embedding_mode": "disabled",
        }],
    }
    save_llm_profiles(payload)
    with open_global_db() as conn:
        persisted = load_global_setting(conn, "llm_profiles")
    serialized = json.dumps(persisted, ensure_ascii=False)
    check(secret not in serialized and "api_key_ref" in serialized, "模型方案只持久化凭据引用")
    hydrated = load_llm_profiles()["profiles"][0]
    check(hydrated["api_key"] == secret, "运行时按引用恢复模型密钥")
    check(hydrated["api_key_last_four"] == "4567", "模型方案保留密钥末四位")
    old_ref = hydrated["api_key_ref"]
    payload["profiles"][0].update(
        {
            "api_key": "sk-profile-rotated-9012",
            "api_key_ref": old_ref,
            "api_key_fingerprint": hydrated["api_key_fingerprint"],
        }
    )
    save_llm_profiles(payload)
    rotated = load_llm_profiles()["profiles"][0]
    check(rotated["api_key_ref"] != old_ref, "密钥轮换使用不可变的新凭据引用")
    check(rotated["api_key"] == "sk-profile-rotated-9012", "密钥轮换后运行时解析新密钥")
    check(not resolve_system_credential(old_ref), "模型方案提交后清理旧凭据引用")


def verify_capability_registry() -> None:
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_CHAT, lambda: CapabilityStatus(CAPABILITY_CHAT, "ready", True, "ok"))
    registry.register(
        CAPABILITY_EMBEDDING,
        lambda: CapabilityStatus(CAPABILITY_EMBEDDING, "missing", False, "未配置"),
    )
    result = negotiate_operation("creative_writing", registry=registry)
    check(result["ready"], "可选向量能力缺失不阻塞创作")
    check(result["degradations"][0]["capability"] == CAPABILITY_EMBEDDING, "能力降级显式可见")
    registry.register(CAPABILITY_CHAT, lambda: CapabilityStatus(CAPABILITY_CHAT, "failed", False, "验证失败"))
    blocked = negotiate_operation("creative_writing", registry=registry)
    check(not blocked["ready"] and blocked["blockers"], "必需能力失败会阻断工作流")


def verify_automatic_configuration() -> None:
    first = configure_operation_automatically(
        "stage5-project",
        "story-main",
        "creative_writing",
        goal="长篇世界观、对白风格与组织冲突",
        source_chars=650_000,
    )
    check(first["settings"]["retrieval_depth"] == "deep", "大规模资料自动选择深检索")
    check("dialogue_style" in first["settings"]["extraction_categories"], "创作目标驱动提取类别")
    original_budget = first["settings"]["context_budget"]
    locked = configure_operation_automatically(
        "stage5-project",
        "story-main",
        "creative_writing",
        goal="短片段",
        source_chars=100,
        locked_fields=["context_budget"],
    )
    check(locked["settings"]["context_budget"] == original_budget, "用户锁定值不被自动配置覆盖")
    check(bool(locked["diff"]), "自动配置保存前后差异")
    revisions = list_automatic_configuration_revisions(
        "stage5-project", "story-main", "creative_writing"
    )
    check(len(revisions) >= 2 and revisions[0]["reasons"], "自动配置保存调整原因和修订链")

    check(
        copy_story_automatic_configurations("stage5-project", "story-main", "story-copy") == 1,
        "复制故事会复制有效自动配置",
    )
    copied = load_automatic_configuration("stage5-project", "story-copy", "creative_writing")
    check(copied["settings"] == locked["settings"], "故事副本继承有效自动配置")
    check(copied["locked_fields"] == locked["locked_fields"], "故事副本继承用户锁定项")
    try:
        copy_story_automatic_configurations("stage5-project", "story-main", "story-copy")
    except ValueError:
        pass
    else:
        raise AssertionError("重复复制自动配置应拒绝覆盖目标修订链")
    check(
        len(list_automatic_configuration_revisions(
            "stage5-project", "story-copy", "creative_writing"
        )) == 1,
        "拒绝重复复制时保留目标自动配置修订链",
    )
    check(
        rename_project_automatic_configurations("stage5-project", "stage5-renamed") == 2,
        "项目重命名会迁移所有故事自动配置键",
    )
    check(
        not load_automatic_configuration("stage5-project", "story-main", "creative_writing"),
        "项目重命名后旧自动配置键不再可见",
    )
    check(
        bool(load_automatic_configuration("stage5-renamed", "story-copy", "creative_writing")),
        "项目重命名后自动配置仍可读取",
    )
    check(
        delete_automatic_configurations("stage5-renamed", story_id="story-copy") == 1,
        "删除故事会级联清理自动配置",
    )


def main() -> int:
    with isolated_workspace("novelforge-capability-orchestration-"):
        initialize_global_db()
        verify_credentials()
        verify_profile_migration()
        verify_capability_registry()
        verify_automatic_configuration()
        with open_global_db() as conn:
            check(get_schema_version(conn) == 15, "全局数据库迁移到阶段5版本")
    print({"ok": True, "checks": CHECKS})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
