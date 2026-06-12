import logging

from rest_framework import serializers

from .crypto import decrypt, encrypt
from .models import DatabaseInstance
from .version_detect import detect_version

logger = logging.getLogger(__name__)


class DatabaseInstanceSerializer(serializers.ModelSerializer):
    """CRUD 序列化器 — 密码字段写入时加密，读取时脱敏。

    创建/更新时自动检测连接并写入 db_version + connection_status。
    """

    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})
    password_masked = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DatabaseInstance
        fields = [
            "id", "name", "db_type", "host", "port",
            "username", "password", "password_masked",
            "environment", "cluster", "is_active",
            "collect_interval", "db_version", "connection_status",
            "last_error", "last_collected_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "db_version", "connection_status", "last_error",
            "last_collected_at", "created_at", "updated_at",
        ]

    def get_password_masked(self, obj):
        return "******"

    def create(self, validated_data):
        raw_pw = validated_data.pop("password")
        validated_data["password"] = encrypt(raw_pw)

        # 先创建实例对象（未保存），用于版本检测
        instance = DatabaseInstance(**validated_data)
        self._probe_connection(instance)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        raw_pw = validated_data.pop("password", None)
        if raw_pw is not None:
            validated_data["password"] = encrypt(raw_pw)

        # 更新字段
        for k, v in validated_data.items():
            setattr(instance, k, v)

        # 如果连接相关字段变化，重新检测
        conn_fields = {"host", "port", "username", "password", "db_type"}
        if conn_fields & set(validated_data.keys()):
            self._probe_connection(instance)

        instance.save()
        return instance

    def _probe_connection(self, instance):
        """检测连接，写入 db_version / connection_status / last_error。"""
        try:
            version_raw, _ = detect_version(instance)
            instance.db_version = version_raw
            instance.connection_status = "connected"
            instance.last_error = ""
        except Exception as e:
            logger.warning(f"[serializer] {instance.name} 连接检测失败: {e}")
            instance.db_version = ""
            instance.connection_status = "disconnected"
            instance.last_error = str(e)


class TestConnectionSerializer(serializers.Serializer):
    """连接测试结果。"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    version = serializers.CharField(required=False, allow_blank=True)
