"""Real import entrypoints freeze the owning session branch before side effects."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.verify_utils import isolated_workspace
from novelforge.services import memory
from novelforge.services.document_parsing import parse_document_bytes
from novelforge.workflows import creative_attachments as imports


@patch.dict("os.environ", {"NOVELFORGE_DISABLE_BACKGROUND_TASKS": "1"})
def main():
    checks = []
    with isolated_workspace("novelforge_attachment_branch_review_"):
        project = memory.create_project("attachment_branch_review")
        story = memory.create_story(project, "Imports", creation_mode="conversational")["story_id"]
        parent = memory.ensure_story_branch(project, story)["branch_id"]
        fork = memory.fork_story_branch(project, story, parent_branch_id=parent, name="Child", allow_current_state=True)
        branch, session = fork["branch"]["branch_id"], fork["session"]["session_id"]
        pasted = imports.import_creative_pasted_text(project, story, session, "Private child material", schedule_knowledge=False)
        assert pasted["branch_id"] == branch and pasted["scope"] == "story"
        checks.append("omitted branch on pasted import follows its child session")
        with memory.open_project_db(memory.project_path(project).resolve()) as conn:
            metadata = json.loads(conn.execute("SELECT metadata_json FROM source_documents WHERE source_id=?", (pasted["source_id"],)).fetchone()[0])
        assert metadata["branch_id"] == branch
        checks.append("raw source ownership is fixed before indexing or extraction")
        document = parse_document_bytes("child.txt", b"Child file knowledge")
        files = imports.import_creative_documents(project, story, session, [document], schedule_knowledge=False)
        assert files[0]["branch_id"] == branch
        checks.append("file import follows the same child ownership contract")
        public = imports.import_creative_pasted_text(project, story, session, "Public material", scope="project", schedule_knowledge=False)
        assert not public.get("story_id") and not public.get("branch_id")
        checks.append("explicit project import remains public instead of acquiring a private branch")
        with patch.object(imports, "ingest_external_source_file") as write:
            try:
                imports.import_creative_pasted_text(project, story, session, "Wrong branch", branch_id=parent, schedule_knowledge=False)
            except ValueError:
                assert not write.called
            else:
                raise AssertionError("foreign branch import accepted")
        checks.append("conflicting branch is rejected before creating a source file")
        memory.archive_story_branch(project, story, branch)
        with patch.object(imports, "ingest_external_source_file") as write:
            try:
                imports.import_creative_pasted_text(project, story, session, "Archived import", schedule_knowledge=False)
            except ValueError:
                assert not write.called
            else:
                raise AssertionError("archived branch import accepted")
        checks.append("archived session import is rejected before side effects")
    print(json.dumps({"ok": True, "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
