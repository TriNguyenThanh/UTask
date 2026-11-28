import logging
from copy import deepcopy

from django.conf import settings
from django.core.cache import cache

from apps.integrations.models import TaskGitHubLink
from apps.integrations.services.operations import pending_operation
from apps.projects.queries.projects import visible_project
from infrastructure.integration import integration_client, source_error

logger = logging.getLogger(__name__)

CACHEABLE_STATUSES = frozenset({"CONNECTED", "PARTIAL"})


def _activity_cache_key(project):
    return f"github-activity:{project.pk}:g{project.github_connection_generation}"


def _read_cached_activity(key):
    try:
        return cache.get(key)
    except Exception as exc:
        logger.warning("GitHub activity cache read failed error=%s", type(exc).__name__)
        return None


def _write_cached_activity(key, value, ttl):
    if ttl <= 0:
        return
    try:
        cache.set(key, value, timeout=ttl)
    except Exception as exc:
        logger.warning("GitHub activity cache write failed error=%s", type(exc).__name__)


def _confirmed_link_maps(project):
    rows = TaskGitHubLink.objects.filter(
        task__project=project,
        task__deleted_at__isnull=True,
        deleted_at__isnull=True,
        confirmation_status="CONFIRMED",
        github_repo_id=project.github_repo_id,
        connection_generation=project.github_connection_generation,
    ).values_list("link_type", "github_ref_id", "task_id")
    branches, commits, pull_requests = {}, [], {}
    for link_type, ref_id, task_id in rows:
        tid = str(task_id)
        if link_type == "BRANCH":
            branches.setdefault(ref_id, set()).add(tid)
        elif link_type == "COMMIT":
            commits.append((ref_id.lower(), tid))
        elif link_type == "PULL_REQUEST":
            pull_requests.setdefault(ref_id, set()).add(tid)
    return branches, commits, pull_requests


def _attach_linked_tasks(project, payload):
    branches_map, commit_links, prs_map = _confirmed_link_maps(project)
    result = deepcopy(payload)
    for branch in result["branches"]:
        branch["linked_task_ids"] = sorted(branches_map.get(branch["name"], ()))
    for commit in result["commits"]:
        sha_lower = commit["id"].lower()
        matched = {
            tid
            for ref_lower, tid in commit_links
            if sha_lower.startswith(ref_lower) or ref_lower.startswith(sha_lower)
        }
        commit["linked_task_ids"] = sorted(matched)
    for pr in result["pull_requests"]:
        pr["linked_task_ids"] = sorted(prs_map.get(pr["id"], ()))
    return result


def _inactive_activity_payload(project, *, status, pending=None):
    prepared = pending.prepared if (pending and pending.prepared) else None
    if prepared and prepared.get("generation") is not None:
        generation = prepared["generation"]
    elif pending and pending.generation is not None:
        generation = pending.generation
    else:
        generation = project.github_connection_generation or 0
    return {
        "project_id": str(project.pk),
        "status": status,
        "repo_id": prepared["repo_id"] if prepared else project.github_repo_id,
        "repo_owner": prepared["repo_owner"] if prepared else project.github_repo_owner,
        "repo_name": prepared["repo_name"] if prepared else project.github_repo_name,
        "default_branch": prepared["default_branch"] if prepared else project.github_default_branch,
        "connection_generation": generation,
        "open_pull_requests_count": 0,
        "branches": [],
        "commits": [],
        "pull_requests": [],
        "issues": [],
        "synced_at": (
            prepared["synced_at"]
            if prepared
            else (project.github_synced_at.isoformat() if project.github_synced_at else None)
        ),
        "cached": False,
    }


def project_github_activity(actor, project_id, bearer):
    project = visible_project(actor, project_id)
    pending = pending_operation(project)
    if pending and pending.state != "ABORT":
        return _inactive_activity_payload(project, status="PENDING", pending=pending)
    if project.github_connection_status != "CONNECTED" or not project.github_repo_id:
        inactive_status = (
            "PENDING" if project.github_connection_status == "PENDING" else "DISCONNECTED"
        )
        return _inactive_activity_payload(project, status=inactive_status)

    ttl = int(getattr(settings, "WORK_GITHUB_ACTIVITY_CACHE_TTL_SECONDS", 45))
    cache_key = _activity_cache_key(project)
    cached_payload = _read_cached_activity(cache_key) if ttl > 0 else None
    if cached_payload is not None:
        enriched = _attach_linked_tasks(project, cached_payload)
        enriched["cached"] = True
        return enriched

    live_payload = integration_client().fetch_project_activity(project_id=project.pk, bearer=bearer)
    if (
        live_payload["connection_generation"] != project.github_connection_generation
        or live_payload["repo_id"] != project.github_repo_id
    ):
        raise source_error("Project activity connection binding mismatch")
    if live_payload["status"] in CACHEABLE_STATUSES:
        _write_cached_activity(cache_key, live_payload, ttl)
    enriched = _attach_linked_tasks(project, live_payload)
    enriched["cached"] = False
    return enriched
