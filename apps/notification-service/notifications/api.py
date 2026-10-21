from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications import clients
from notifications.models import Notification, Preference


class PreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Preference
        fields = ["assignment", "deadline", "mention", "feedback"]

    def to_internal_value(self, data):
        if (
            not isinstance(data, dict)
            or set(data) - set(self.fields)
            or any(type(v) is not bool for v in data.values())
        ):
            raise serializers.ValidationError(
                {"non_field_errors": ["Các tùy chọn phải là boolean hợp lệ."]}
            )
        return super().to_internal_value(data)


def visible(user_id, unread_only=False, read_filter=None):
    items = []
    query = Notification.objects.filter(user_id=user_id, inbox__status="processed").exclude(
        inbox__envelope__has_key="redacted"
    )
    if read_filter is not None:
        query = query.filter(read=read_filter)
    if unread_only:
        query = query.filter(read=False)
    rows = list(query.select_related("inbox").order_by("-created_at", "-id"))
    # Always resolve against Work before exposing any title, body or target.
    for row, result in zip(rows, clients.resolve_many(rows, user_id), strict=True):
        if result is not None:
            items.append(
                {
                    "id": str(row.id),
                    "category": "task-pr",
                    "title": result["title"],
                    "body": result["body"],
                    "at": row.created_at.isoformat(),
                    "read": row.read,
                    "actionLabel": "Xem chi tiết" if result.get("target") else None,
                    "target": result.get("target"),
                }
            )
    return items


class Listing(APIView):
    def get(self, request):
        read_filter = request.query_params.get("read")
        if read_filter not in (None, "true", "false"):
            raise ValidationError({"read": "Chỉ chấp nhận true hoặc false."})
        items = visible(
            request.user.id, read_filter=None if read_filter is None else read_filter == "true"
        )
        paginator = PageNumberPagination()
        paginator.page_size = 25
        page = paginator.paginate_queryset(items, request)
        return paginator.get_paginated_response(page)


class Unread(APIView):
    def get(self, request):
        return Response(
            {"count": sum(not item["read"] for item in visible(request.user.id, unread_only=True))}
        )


class MarkRead(APIView):
    def post(self, request, notification_id):
        row = get_object_or_404(Notification, pk=notification_id, user_id=request.user.id)
        Notification.objects.filter(pk=row.pk, user_id=request.user.id).update(read=True)
        return Response({"read": True})


class ReadAll(APIView):
    def post(self, request):
        Notification.objects.filter(user_id=request.user.id, read=False).update(read=True)
        return Response({"read": True})


class Preferences(APIView):
    def get(self, request):
        row, _ = Preference.objects.get_or_create(user_id=request.user.id)
        return Response(PreferencesSerializer(row).data)

    def patch(self, request):
        row, _ = Preference.objects.get_or_create(user_id=request.user.id)
        serializer = PreferencesSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class Health(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok"})


urlpatterns = [
    path("", Listing.as_view()),
    path("unread-count", Unread.as_view()),
    path("read-all", ReadAll.as_view()),
    path("<uuid:notification_id>/read", MarkRead.as_view()),
    path("preferences", Preferences.as_view()),
    path("health", Health.as_view()),
    path("healthz", Health.as_view()),
]
