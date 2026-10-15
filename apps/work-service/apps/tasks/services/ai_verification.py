from apps.messaging.services import lookup_receipt
from apps.tasks.queries import applied_action_receipt, applied_local_ids
from infrastructure.ai import ai_client


def verified_proof(actor, project_id, payload, scope, *, parent_id=None):
    if lookup_receipt(scope, payload):
        return None
    field = "subtasks" if parent_id else "tasks"
    requested = {item["local_id"] for item in payload[field]}
    persisted = applied_local_ids(project_id, payload["proposal_id"], requested)
    if requested == persisted:
        return None
    return ai_client().verify(
        actor=actor,
        project_id=project_id,
        proposal_id=payload["proposal_id"],
        kind="SUBTASK" if parent_id else "BACKLOG",
        parent_id=parent_id,
    )


def verified_action_proof(actor, project_id, payload, scope):
    prior = lookup_receipt(scope, payload) or applied_action_receipt(
        project_id, payload["proposal_id"], payload["item_id"]
    )
    if prior:
        return None
    return ai_client().verify(
        actor=actor, project_id=project_id, proposal_id=payload["proposal_id"], kind="ACTION"
    )
