from django.db.models import CharField, Count, IntegerField, OuterRef, Subquery, UUIDField, Value
from django.db.models.functions import Coalesce

from apps.courses.filters import ClassSectionFilter, apply_filterset, list_status
from apps.courses.models import ClassSection, ClassTeacher, Enrollment
from apps.courses.permissions import actor_roles, is_teacher, require_read, visible_classes
from apps.courses.serializers.classes import ClassSerializer, TeacherSerializer
from apps.groups.models import GroupMember, StudyGroup
from common.pagination import paginate


def annotate_classes(queryset, *, actor_id=None):
    enrolled_subquery = (
        Enrollment.objects.filter(class_section_id=OuterRef("pk"), status="ACTIVE")
        .values("class_section_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    active_group_subquery = (
        StudyGroup.objects.filter(class_section_id=OuterRef("pk"), status="ACTIVE")
        .values("class_section_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    primary_teacher_subquery = (
        ClassTeacher.objects.filter(
            class_section_id=OuterRef("pk"), status="ACTIVE", role="PRIMARY"
        )
        .order_by("assigned_at", "id")
        .values("user_id")[:1]
    )
    fallback_teacher_subquery = (
        ClassTeacher.objects.filter(class_section_id=OuterRef("pk"), status="ACTIVE")
        .order_by("assigned_at", "id")
        .values("user_id")[:1]
    )
    annotations = {
        "_enrolled_count": Coalesce(
            Subquery(enrolled_subquery, output_field=IntegerField()), Value(0)
        ),
        "_active_group_count": Coalesce(
            Subquery(active_group_subquery, output_field=IntegerField()), Value(0)
        ),
        "_primary_teacher_id": Coalesce(
            Subquery(primary_teacher_subquery, output_field=UUIDField()),
            Subquery(fallback_teacher_subquery, output_field=UUIDField()),
        ),
    }
    if actor_id is not None:
        my_membership = GroupMember.objects.filter(
            class_section_id=OuterRef("pk"),
            enrollment__user_id=actor_id,
            enrollment__status="ACTIVE",
            status="ACTIVE",
            group__status="ACTIVE",
        )
        annotations["_my_group_id"] = Subquery(
            my_membership.values("group_id")[:1], output_field=UUIDField()
        )
        annotations["_my_group_name"] = Subquery(
            my_membership.values("group__name")[:1], output_field=CharField()
        )
    else:
        annotations["_my_group_id"] = Value(None, output_field=UUIDField())
        annotations["_my_group_name"] = Value(None, output_field=CharField())
    return queryset.select_related("course").annotate(**annotations)


def list_classes(request):
    qs, filters = apply_filterset(
        ClassSectionFilter, request.query_params, visible_classes(request)
    )
    qs = annotate_classes(qs, actor_id=request.user.id)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={"actor": str(request.user.id), "resource": "classes", **filters},
    )
    return ClassSerializer(rows, many=True).data, meta


def class_detail(request, section):
    require_read(request, section)
    target = (
        annotate_classes(ClassSection.objects.filter(pk=section.pk), actor_id=request.user.id).get()
        if isinstance(section, ClassSection)
        else section
    )
    return ClassSerializer(target, context={"actor_id": request.user.id}).data


def class_teachers(request, section):
    require_read(request, section)
    active_only = not (
        is_teacher(request.user, section, roles=actor_roles(request))
        or "SYSTEM_ADMIN" in actor_roles(request)
    )
    status = list_status(request.query_params, {"ACTIVE", "LEFT"})
    qs = section.teachers.all()
    if active_only:
        qs = qs.filter(status="ACTIVE")
    if status is not None:
        qs = qs.filter(status=status)
    rows, meta = paginate(
        qs,
        request.query_params,
        scope={
            "actor": str(request.user.id),
            "class": str(section.pk),
            "resource": "teachers",
            "status": status,
            "active_only": active_only,
        },
        time_field="assigned_at",
    )
    return TeacherSerializer(rows, many=True).data, meta
