class WorkflowCancelled(RuntimeError):
    """Raised when a user cancels a workflow before persistence."""


def raise_if_cancelled(cancel_check) -> None:
    if cancel_check and cancel_check():
        raise WorkflowCancelled("workflow_cancelled")
