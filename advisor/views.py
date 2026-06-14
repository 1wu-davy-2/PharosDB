"""安全巡检 API — 规则管理与结果查询。"""

from rest_framework import permissions, status, views
from rest_framework.response import Response

from .models import AdvisorCheck, AdvisorFinding
from .runner import run_all_checks, run_check_on_instance


class CheckListView(views.APIView):
    """GET /api/advisor/checks/ — 所有巡检规则及最近统计。"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        checks = AdvisorCheck.objects.all().order_by("category", "severity", "name")

        data = []
        for c in checks:
            findings = AdvisorFinding.objects.filter(advisor_check=c, resolved_at__isnull=True)
            data.append({
                "id": c.id,
                "name": c.name,
                "display_name": c.display_name,
                "summary": c.summary,
                "description": c.description,
                "family": c.family,
                "category": c.category,
                "severity": c.severity,
                "interval": c.interval,
                "mode": c.mode,
                "enabled": c.enabled,
                "active_findings": findings.count(),
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            })

        return Response({
            "checks": data,
            "total": len(data),
            "categories": sorted(set(c.category for c in checks)),
        })


class FindingListView(views.APIView):
    """GET /api/advisor/findings/ — 巡检发现列表。

    ?severity=critical,error &family=mysql &instance_id=1 &category=security
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = AdvisorFinding.objects.select_related("advisor_check", "instance").all()

        severity = request.query_params.get("severity", "")
        if severity:
            qs = qs.filter(severity__in=severity.split(","))

        family = request.query_params.get("family", "")
        if family:
            qs = qs.filter(advisor_check__family=family)

        instance_id = request.query_params.get("instance_id", "")
        if instance_id:
            qs = qs.filter(instance_id=int(instance_id))

        category = request.query_params.get("category", "")
        if category:
            qs = qs.filter(advisor_check__category=category)

        resolved = request.query_params.get("resolved", "false").lower()
        if resolved != "true":
            qs = qs.filter(resolved_at__isnull=True)

        limit = int(request.query_params.get("limit", 50))
        qs = qs.order_by("-found_at")[:limit]

        data = []
        for f in qs:
            data.append({
                "id": f.id,
                "check_name": f.advisor_check.name,
                "check_display": f.advisor_check.display_name,
                "category": f.advisor_check.category,
                "family": f.advisor_check.family,
                "severity": f.severity,
                "summary": f.summary,
                "detail": (f.detail or "")[:2000],
                "labels": f.labels,
                "instance_id": f.instance_id,
                "instance_name": f.instance.name,
                "instance_type": f.instance.db_type,
                "found_at": f.found_at.isoformat(),
                "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
            })

        return Response({"findings": data, "count": len(data)})


class SummaryView(views.APIView):
    """GET /api/advisor/summary/ — 巡检概览统计。"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Count

        findings = AdvisorFinding.objects.filter(resolved_at__isnull=True)

        by_severity = {}
        for sev in ["critical", "error", "warning", "info"]:
            by_severity[sev] = findings.filter(severity=sev).count()

        by_category = {}
        for row in findings.values("advisor_check__category").annotate(cnt=Count("id")):
            by_category[row["advisor_check__category"]] = row["cnt"]

        by_instance = []
        for row in findings.values("instance__name", "instance__db_type").annotate(cnt=Count("id")).order_by("-cnt"):
            by_instance.append({
                "name": row["instance__name"],
                "db_type": row["instance__db_type"],
                "count": row["cnt"],
            })

        recent = []
        for f in findings.order_by("-found_at")[:10]:
            recent.append({
                "id": f.id,
                "check_display": f.advisor_check.display_name,
                "instance_name": f.instance.name,
                "severity": f.severity,
                "summary": f.summary,
                "found_at": f.found_at.isoformat(),
            })

        return Response({
            "total": findings.count(),
            "by_severity": by_severity,
            "by_category": by_category,
            "by_instance": by_instance,
            "recent": recent,
        })


class RunCheckView(views.APIView):
    """POST /api/advisor/run/ — 手动触发巡检。

    {"action": "all"}  或  {"action": "single", "check_name": "...", "instance_id": 1}
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        action = request.data.get("action", "all")

        if action == "all":
            count = run_all_checks()
            return Response({"status": "ok", "findings": count})

        if action == "single":
            check_name = request.data.get("check_name", "")
            instance_id = request.data.get("instance_id")
            if not check_name or not instance_id:
                return Response({"error": "请提供 check_name 和 instance_id"}, status=400)
            finding = run_check_on_instance(check_name, int(instance_id))
            return Response({
                "status": "ok",
                "found": finding is not None,
                "finding_id": finding.id if finding else None,
            })

        return Response({"error": f"未知 action: {action}"}, status=400)


class ToggleCheckView(views.APIView):
    """POST /api/advisor/checks/toggle/ — 启停巡检规则。

    {"name": "mysql_anonymous_user", "enabled": false}
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        name = request.data.get("name", "")
        enabled = request.data.get("enabled", True)
        try:
            check = AdvisorCheck.objects.get(name=name)
            check.enabled = enabled
            check.save(update_fields=["enabled", "updated_at"])
            return Response({"status": "ok", "enabled": enabled})
        except AdvisorCheck.DoesNotExist:
            return Response({"error": "规则不存在"}, status=404)
