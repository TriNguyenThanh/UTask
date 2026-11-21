"""HTTP endpoints for notifications, read state and email preferences."""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import Notification, Preference
from notifications.queries import visible
from notifications.serializers import PreferencesSerializer


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
