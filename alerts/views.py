from django.db.models import Count
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from .models import AlertEvent, AlertRule
from .serializers import AlertEventSerializer, AlertRuleSerializer


class AlertRuleViewSet(ModelViewSet):
    queryset         = AlertRule.objects.select_related("instance").order_by("-created_at")
    serializer_class = AlertRuleSerializer

    @action(detail=True, methods=["post"], url_path="test")
    def test_evaluate(self, request, pk=None):
        """手动触发一次规则评估，不写事件，仅返回当前指标值。"""
        from .evaluator import _query_metric
        from collector.models import DatabaseInstance

        rule    = self.get_object()
        targets = [rule.instance] if rule.instance_id else list(
            DatabaseInstance.objects.filter(is_active=True)
        )
        results = []
        for inst in targets:
            if inst is None:
                continue
            value = _query_metric(rule, inst)
            results.append({
                "instance":     inst.name,
                "metric_value": value,
                "threshold":    rule.threshold,
                "would_fire":   value is not None and value > rule.threshold,
            })
        return Response({"rule": rule.name, "results": results})

    @action(detail=True, methods=["post"], url_path="toggle")
    def toggle_enabled(self, request, pk=None):
        rule            = self.get_object()
        rule.is_enabled = not rule.is_enabled
        rule.save(update_fields=["is_enabled"])
        return Response({"is_enabled": rule.is_enabled})


class AlertEventViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    serializer_class = AlertEventSerializer

    def get_queryset(self):
        qs = AlertEvent.objects.select_related("rule", "instance").order_by("-fired_at")
        if s := self.request.query_params.get("status"):
            qs = qs.filter(status=s)
        if r := self.request.query_params.get("rule_id"):
            qs = qs.filter(rule_id=r)
        if i := self.request.query_params.get("instance_id"):
            qs = qs.filter(instance_id=i)
        return qs

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """首页告警汇总：firing 数量 × 严重级别。"""
        data = (
            AlertEvent.objects
            .filter(status="firing")
            .values("rule__severity")
            .annotate(count=Count("id"))
        )
        result = {"warning": 0, "critical": 0}
        for row in data:
            result[row["rule__severity"]] = row["count"]
        result["total"] = result["warning"] + result["critical"]
        return Response(result)
