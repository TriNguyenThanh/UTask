from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Commit, PullRequest, Repository
from .serializers import CommitSerializer, PullRequestSerializer, RepositorySerializer


class RepositoryListCreateView(APIView):
    def get(self, _request):
        return Response(RepositorySerializer(Repository.objects.all(), many=True).data)

    def post(self, request):
        serializer = RepositorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(RepositorySerializer(serializer.save()).data, status=201)


class CommitCreateView(APIView):
    def post(self, request, repository_id):
        serializer = CommitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(repository=get_object_or_404(Repository, id=repository_id))
        return Response(CommitSerializer(item).data, status=201)


class PullRequestCreateView(APIView):
    def post(self, request, repository_id):
        serializer = PullRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(repository=get_object_or_404(Repository, id=repository_id))
        return Response(PullRequestSerializer(item).data, status=201)


class GitHubActivityView(APIView):
    def get(self, _request, project_id):
        repositories = Repository.objects.filter(project_id=project_id)
        return Response(
            {
                "project_id": project_id,
                "commits": CommitSerializer(
                    Commit.objects.filter(repository__in=repositories), many=True
                ).data,
                "pull_requests": PullRequestSerializer(
                    PullRequest.objects.filter(repository__in=repositories), many=True
                ).data,
            }
        )
