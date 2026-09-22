from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project

from .models import Task
from .serializers import TaskSerializer


class ProjectTasksView(APIView):
    def get(self, _request, project_id):
        get_object_or_404(Project, id=project_id)
        return Response(TaskSerializer(Task.objects.filter(project_id=project_id), many=True).data)

    def post(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        serializer = TaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save(project=project)
        return Response(TaskSerializer(task).data, status=201)


class TaskDetailView(APIView):
    def patch(self, request, task_id):
        task = get_object_or_404(Task, id=task_id)
        serializer = TaskSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(TaskSerializer(serializer.save()).data)
