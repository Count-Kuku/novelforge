"""Branch configuration stays editable without mutating its frozen parent."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.verify_utils import isolated_workspace
from novelforge.services import memory
from novelforge.workflows.context_assembly import assemble_generation_context, render_context_for_prompt


@patch.dict("os.environ", {"NOVELFORGE_DISABLE_BACKGROUND_TASKS": "1"})
def main():
    checks = []
    with isolated_workspace("novelforge_branch_config_review_"):
        project = memory.create_project("branch_config_review")
        story = memory.create_story(project, "Configuration", creation_mode="conversational")["story_id"]
        parent = memory.ensure_story_branch(project, story)["branch_id"]
        memory.save_creative_profile(project, {"notes": "PARENT_PROFILE_BEFORE"}, story)
        memory.save_story_rules(project, story, {"all": ["PARENT_RULE_BEFORE"]})
        child = memory.fork_story_branch(project, story, parent_branch_id=parent, name="Child", allow_current_state=True)["branch"]["branch_id"]
        assert memory.load_effective_story_branch_configuration(project, story, child)["profile"]["notes"] == "PARENT_PROFILE_BEFORE"
        checks.append("first fork without a previous checkpoint captures the parent configuration")
        memory.save_creative_profile(project, {"notes": "PARENT_PROFILE_AFTER"}, story)
        memory.save_story_rules(project, story, {"all": ["PARENT_RULE_AFTER"]})
        frozen = memory.load_effective_story_branch_configuration(project, story, child)
        assert frozen["profile"]["notes"] == "PARENT_PROFILE_BEFORE", frozen
        checks.append("parent edits do not rewrite child configuration")
        memory.save_story_branch_configuration(project, story, child, {"profile": {**frozen["profile"], "notes": "CHILD_PROFILE"}, "story_rules": {"all": ["CHILD_RULE"]}})
        current = memory.load_effective_story_branch_configuration(project, story, child)
        assert current["profile"]["notes"] == "CHILD_PROFILE" and "CHILD_RULE" in str(current["story_rules"])
        assert memory.load_creative_profile(project, story)["notes"] == "PARENT_PROFILE_AFTER"
        checks.append("child current settings save independently")
        def text(branch):
            return render_context_for_prompt(assemble_generation_context(project, story_id=story, branch_id=branch, capability="creative_writing", query="continue", retrieval_mode="lexical", enable_entity_planning=False))
        child_text = text(child)
        assert "CHILD_RULE" in child_text and "PARENT_RULE_AFTER" not in child_text
        checks.append("generation consumes the current child rule override")
        parent_text = text(parent)
        assert "PARENT_RULE_AFTER" in parent_text and "CHILD_RULE" not in parent_text
        checks.append("ordinary main-story settings edits still take effect")
        memory.create_story_checkpoint(project, story, child, allow_current_state=True)
        grandchild = memory.fork_story_branch(project, story, parent_branch_id=child, name="Grandchild", allow_current_state=True)["branch"]["branch_id"]
        assert memory.load_effective_story_branch_configuration(project, story, grandchild)["profile"]["notes"] == "CHILD_PROFILE"
        checks.append("a later fork inherits the edited child configuration")
        memory.save_story_branch_configuration(project, story, child, {"story_rules": {"all": ["CHILD_RULE_LATER"]}})
        assert "CHILD_RULE_LATER" not in text(grandchild)
        checks.append("later edits do not alter an existing descendant")
        later = memory.fork_story_branch(project, story, parent_branch_id=parent, name="Later current state", allow_current_state=True)["branch"]["branch_id"]
        assert memory.load_effective_story_branch_configuration(project, story, later)["profile"]["notes"] == "PARENT_PROFILE_AFTER"
        checks.append("explicit current-state fork captures current configuration even with an older head")
        memory.archive_story_branch(project, story, grandchild)
        memory.archive_story_branch(project, story, child)
        try:
            memory.save_story_branch_configuration(project, story, child, {"story_rules": {}})
        except ValueError:
            checks.append("archived branch configuration is read-only")
        else:
            raise AssertionError("archived branch accepted configuration write")
    print(json.dumps({"ok": True, "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
