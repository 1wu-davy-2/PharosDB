"""SystemConfig 序列化器。"""

from rest_framework import serializers

from .models import SystemConfig


class SystemConfigSerializer(serializers.ModelSerializer):
    typed_value = serializers.SerializerMethodField()

    class Meta:
        model = SystemConfig
        fields = [
            "id", "key", "value", "value_type", "typed_value",
            "display_name", "description", "category", "editable",
            "updated_at",
        ]
        read_only_fields = ["id", "key", "value_type", "updated_at"]

    def get_typed_value(self, obj):
        return obj.to_typed()
