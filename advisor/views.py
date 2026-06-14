"""安全巡检 API — 规则管理、分组定向、调度控制、结果查询。"""

from rest_framework import permissions, status, views
from rest_framework.response import Response

from .models import AdvisorCheck, AdvisorFinding, InstanceGroup, ScheduledRunLog
from .runner import run_all_checks, run_check_on_instance, run_check_for_group


# ═══════════════════════════════════════════════════════════════════
# 巡检规则
# ═══════════════════════════════════════════════════════════════════

class CheckListView(views.APIView):
    """GET /api/advisor/checks/ — 所有巡检规则及最近统计。"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        checks = AdvisorCheck.objects.all().prefetch_related("target_groups").order_by("category", "severity", "name")

        data = []
        for c in checks:
            findings = AdvisorFinding.objects.filter(advisor_check=c, resolved_at__isnull=True)
            target_groups = [
                {"id": g.id, "name": g.name}
                for g in c.target_groups.all()
            ]
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
                "target_groups": target_groups,
                "targets_all": not c.target_groups.exists(),
                "last_scheduled_run_at": c.last_scheduled_run_at.isoformat() if c.last_scheduled_run_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            })

        return Response({
            "checks": data,
            "total": len(data),
            "categories": sorted(set(c.category for c in checks)),
        })


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

            # 同步调度器
            try:
                from .scheduler import advisor_registry
                advisor_registry.update_check(check.id, check.interval, enabled)
            except Exception:
                pass

            return Response({"status": "ok", "enabled": enabled})
        except AdvisorCheck.DoesNotExist:
            return Response({"error": "规则不存在"}, status=404)


class CheckTargetingView(views.APIView):
    """PUT /api/advisor/checks/<id>/targeting/ — 配置巡检规则的目标分组。

    {"group_ids": [1, 2]}  空数组 = 全部实例
    """

    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        try:
            check = AdvisorCheck.objects.get(pk=pk)
        except AdvisorCheck.DoesNotExist:
            return Response({"error": "规则不存在"}, status=404)

        group_ids = request.data.get("group_ids", [])
        check.target_groups.set(group_ids)
        check.save(update_fields=["updated_at"])

        target_groups = [
            {"id": g.id, "name": g.name}
            for g in check.target_groups.all()
        ]
        return Response({
            "status": "ok",
            "check_id": check.id,
            "target_groups": target_groups,
            "targets_all": not check.target_groups.exists(),
        })


# ═══════════════════════════════════════════════════════════════════
# 巡检发现
# ═══════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════
# 执行巡检
# ═══════════════════════════════════════════════════════════════════

class RunCheckView(views.APIView):
    """POST /api/advisor/run/ — 手动触发巡检。

    {"action": "all"}  或  {"action": "single", "check_name": "...", "instance_id": 1}
    或  {"action": "group", "group_id": 1}
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

        if action == "group":
            group_id = request.data.get("group_id")
            if not group_id:
                return Response({"error": "请提供 group_id"}, status=400)
            try:
                group = InstanceGroup.objects.get(pk=int(group_id))
            except InstanceGroup.DoesNotExist:
                return Response({"error": "分组不存在"}, status=404)

            total_findings = 0
            checks = AdvisorCheck.objects.filter(enabled=True).prefetch_related("target_groups")
            for check in checks:
                # 检查该规则是否定向到该分组（或定向全部）
                if check.target_groups.exists() and not check.target_groups.filter(pk=group.pk).exists():
                    continue
                count = run_check_for_group(check, group)
                total_findings += count

            return Response({"status": "ok", "findings": total_findings, "group_name": group.name})

        return Response({"error": f"未知 action: {action}"}, status=400)


# ═══════════════════════════════════════════════════════════════════
# 实例分组 CRUD
# ═══════════════════════════════════════════════════════════════════

class GroupListView(views.APIView):
    """GET /api/advisor/groups/ — 列出所有分组。
    POST /api/advisor/groups/ — 创建分组。
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        groups = InstanceGroup.objects.prefetch_related("instances", "checks").all()

        data = []
        for g in groups:
            instances = g.instances.all()
            data.append({
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "instance_count": instances.count(),
                "instances": [
                    {
                        "id": i.id, "name": i.name, "db_type": i.db_type,
                        "environment": i.environment, "cluster": i.cluster,
                        "cluster_role": i.cluster_role,
                        "connection_status": i.connection_status,
                    }
                    for i in instances
                ],
                "check_count": g.checks.count(),
                "created_at": g.created_at.isoformat(),
                "updated_at": g.updated_at.isoformat(),
            })

        return Response({"groups": data, "total": len(data)})

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"error": "组名不能为空"}, status=400)

        if InstanceGroup.objects.filter(name=name).exists():
            return Response({"error": "组名已存在"}, status=400)

        description = request.data.get("description", "")
        instance_ids = request.data.get("instance_ids", [])

        group = InstanceGroup.objects.create(name=name, description=description)
        if instance_ids:
            group.instances.set(instance_ids)

        return Response({
            "status": "ok",
            "group": _group_to_dict(group),
        })


class GroupDetailView(views.APIView):
    """PUT /api/advisor/groups/<id>/ — 更新分组。
    DELETE /api/advisor/groups/<id>/ — 删除分组。
    """

    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        try:
            group = InstanceGroup.objects.get(pk=pk)
        except InstanceGroup.DoesNotExist:
            return Response({"error": "分组不存在"}, status=404)

        name = (request.data.get("name") or "").strip()
        if name and name != group.name and InstanceGroup.objects.filter(name=name).exists():
            return Response({"error": "组名已存在"}, status=400)

        if name:
            group.name = name
        if "description" in request.data:
            group.description = request.data.get("description", "")
        group.save()

        if "instance_ids" in request.data:
            group.instances.set(request.data.get("instance_ids", []))

        return Response({
            "status": "ok",
            "group": _group_to_dict(group),
        })

    def delete(self, request, pk):
        try:
            group = InstanceGroup.objects.get(pk=pk)
        except InstanceGroup.DoesNotExist:
            return Response({"error": "分组不存在"}, status=404)

        group.delete()
        return Response({"status": "ok"})


def _group_to_dict(group):
    """序列化单个 InstanceGroup 为 dict。"""
    instances = group.instances.all()
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "instance_count": instances.count(),
        "instances": [
            {
                "id": i.id, "name": i.name, "db_type": i.db_type,
                "environment": i.environment, "cluster": i.cluster,
                "cluster_role": i.cluster_role,
                "connection_status": i.connection_status,
            }
            for i in instances
        ],
        "check_count": group.checks.count(),
        "created_at": group.created_at.isoformat(),
        "updated_at": group.updated_at.isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
# 调度器控制
# ═══════════════════════════════════════════════════════════════════

class SchedulerStatusView(views.APIView):
    """GET /api/advisor/scheduler/status/ — 调度器状态 + 最近的执行日志。"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            from .scheduler import advisor_registry
            sched_status = advisor_registry.status()
        except Exception:
            sched_status = {"running": False, "active_checks": 0, "checks": []}

        # 最近 20 条执行日志
        recent_runs = []
        for log in ScheduledRunLog.objects.select_related("advisor_check", "instance_group")[:20]:
            recent_runs.append({
                "id": log.id,
                "check_name": log.advisor_check.name,
                "check_display": log.advisor_check.display_name,
                "group_name": log.instance_group.name if log.instance_group else "全部",
                "instances_checked": log.instances_checked,
                "findings_created": log.findings_created,
                "status": log.status,
                "duration_ms": log.duration_ms,
                "started_at": log.started_at.isoformat(),
                "finished_at": log.finished_at.isoformat() if log.finished_at else None,
            })

        return Response({
            **sched_status,
            "recent_runs": recent_runs,
        })


class SchedulerToggleView(views.APIView):
    """POST /api/advisor/scheduler/toggle/ — 启停调度器。

    {"enabled": true}
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        enabled = request.data.get("enabled", True)
        from .scheduler import advisor_registry

        if enabled:
            advisor_registry.start()
        else:
            advisor_registry.stop()

        return Response({
            "status": "ok",
            "running": advisor_registry.running,
        })
