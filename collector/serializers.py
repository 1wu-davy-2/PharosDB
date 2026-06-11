from rest_framework import serializers

from .crypto import decrypt, encrypt
from .models import DatabaseInstance


class DatabaseInstanceSerializer(serializers.ModelSerializer):
    """CRUD 序列化器 — 密码字段写入时加密，读取时脱敏。"""

    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})
    password_masked = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DatabaseInstance
        fields = [
            "id", "name", "db_type", "host", "port",
            "username", "password", "password_masked",
            "environment", "cluster", "is_active",
            "collect_interval", "last_collected_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "last_collected_at", "created_at", "updated_at"]

    def get_password_masked(self, obj):
        return "******"

    def create(self, validated_data):
        raw_pw = validated_data.pop("password")
        validated_data["password"] = encrypt(raw_pw)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        raw_pw = validated_data.pop("password", None)
        if raw_pw is not None:
            validated_data["password"] = encrypt(raw_pw)
        return super().update(instance, validated_data)


class TestConnectionSerializer(serializers.Serializer):
    """连接测试结果。"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    version = serializers.CharField(required=False, allow_blank=True)
