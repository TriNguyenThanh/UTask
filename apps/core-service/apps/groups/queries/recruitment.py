from django.db.models import BooleanField, CharField, OuterRef, Q, Subquery
from django.db.models.expressions import RawSQL

from apps.courses.models import Enrollment
from apps.courses.permissions import require_read
from apps.groups.models import GroupJoinRequest, StudyGroup
from apps.groups.queries.groups import annotate_groups
from apps.groups.queries.profiles import fetch_user_profiles
from apps.groups.serializers.recruitment import OpenGroupSerializer, UnassignedStudentSerializer
from apps.groups.serializers.validators import build_minimal_profile
from common.pagination import paginate


def list_open_groups(request, section):
    require_read(request, section)
    search = (request.query_params.get("search") or "").strip()
    skill = (request.query_params.get("skill") or "").strip()
    qs = annotate_groups(
        StudyGroup.objects.filter(class_section=section, status="ACTIVE", is_recruiting=True)
    ).filter(_member_count__lt=section.group_max_size)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(recruitment_note__icontains=search))
    if skill:
        qs = qs.annotate(
            _has_skill=RawSQL(
                'EXISTS (SELECT 1 FROM jsonb_array_elements_text("study_groups"."needed_skills") '
                "AS elem WHERE LOWER(elem) = LOWER(%s))",
                [skill],
                output_field=BooleanField(),
            )
        ).filter(_has_skill=True)
    enrollment = Enrollment.objects.filter(
        class_section=section, user_id=request.user.id, status="ACTIVE"
    ).first()
    if enrollment is not None:
        my_status = (
            GroupJoinRequest.objects.filter(
                class_section=section,
                group_id=OuterRef("pk"),
                enrollment=enrollment,
            )
            .order_by("-created_at", "-id")
            .values("status")[:1]
        )
        qs = qs.annotate(_my_request_status=Subquery(my_status, output_field=CharField()))
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "resource": "open-groups",
            "search": search or None,
            "skill": skill.casefold() or None,
        },
    )
    profiles = fetch_user_profiles([row._leader_id for row in rows if row._leader_id])
    items = [
        {
            "id": row.pk,
            "name": row.name,
            "member_count": row._member_count,
            "max_size": section.group_max_size,
            "leader_profile": (
                build_minimal_profile(row._leader_id, profiles.get(str(row._leader_id)))
                if row._leader_id is not None
                else None
            ),
            "recruitment_note": row.recruitment_note,
            "needed_skills": list(row.needed_skills or []),
            "my_request_status": getattr(row, "_my_request_status", None),
        }
        for row in rows
    ]
    return OpenGroupSerializer(items, many=True).data, meta


def list_unassigned_students(request, section):
    require_read(request, section)
    qs = Enrollment.objects.filter(class_section=section, status="ACTIVE").exclude(
        memberships__status="ACTIVE", memberships__group__status="ACTIVE"
    )
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "resource": "unassigned-students",
        },
        time_field="enrolled_at",
    )
    profiles = fetch_user_profiles([row.user_id for row in rows])
    items = [build_minimal_profile(row.user_id, profiles.get(str(row.user_id))) for row in rows]
    return UnassignedStudentSerializer(items, many=True).data, meta
