from rest_framework import serializers
from common.serializers import StrictInputSerializer

class JoinCodeSerializer(StrictInputSerializer):
    code = serializers.CharField(max_length=100)
