from rest_framework import serializers

from .models import AlertEvent, AlertRule


class AlertRuleSerializer(serializers.ModelSerializer):
    rule_type_display = serializers.CharField(source="get_rule_type_display", read_only=True)
    severity_display  = serializers.CharField(source="get_severity_display",  read_only=True)
    instance_name     = serializers.SerializerMethodField()
    firing_count      = serializers.SerializerMethodField()

    class Meta:
        model  = AlertRule
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at")

    def get_instance_name(self, obj):
        return obj.instance.name if obj.instance_id else None

    def get_firing_count(self, obj):
        return obj.events.filter(status="firing").count()

    def validate(self, attrs):
        if attrs.get("rule_type") == "custom_sql" and not attrs.get("custom_sql", "").strip():
            raise serializers.ValidationError({"custom_sql": "自定义 SQL 类型必须填写 custom_sql 内容"})
        return attrs


class AlertEventSerializer(serializers.ModelSerializer):
    rule_name     = serializers.CharField(source="rule.name",     read_only=True)
    rule_type     = serializers.CharField(source="rule.rule_type", read_only=True)
    severity      = serializers.CharField(source="rule.severity",  read_only=True)
    instance_name = serializers.SerializerMethodField()
    duration      = serializers.IntegerField(source="duration_seconds", read_only=True)

    class Meta:
        model  = AlertEvent
        fields = "__all__"
        read_only_fields = ("fired_at", "resolved_at", "notified", "notify_error")

    def get_instance_name(self, obj):
        return obj.instance.name if obj.instance_id else None
