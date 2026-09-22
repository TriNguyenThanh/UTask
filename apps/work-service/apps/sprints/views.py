from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project

from .models import Sprint


class ProjectSprintsView(APIView):
    def get(self, _request, project_id):
        get_object_or_404(Project, id=project_id)
        return Response(
            [
                {
                    "id": item.id,
                    "name": item.name,
                    "start_date": item.start_date,
                    "end_date": item.end_date,
                }
                for item in Sprint.objects.filter(project_id=project_id)
            ]
        )
