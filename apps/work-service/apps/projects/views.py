from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Project
from .serializers import ProjectMemberSerializer, ProjectSerializer


class ProjectListCreateView(APIView):
    def get(self, _request):
        return Response(ProjectSerializer(Project.objects.all(), many=True).data)

    def post(self, request):
        serializer = ProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        return Response(ProjectSerializer(project).data, status=201)


class ProjectDetailView(APIView):
    def get(self, _request, project_id):
        return Response(ProjectSerializer(get_object_or_404(Project, id=project_id)).data)


class ProjectMembersView(APIView):
    def get(self, _request, project_id):
        project = get_object_or_404(Project, id=project_id)
        return Response(ProjectMemberSerializer(project.members.all(), many=True).data)
