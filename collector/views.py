from rest_framework import serializers as drf_serializers
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .crypto import decrypt
from .models import CollectionHistory, DatabaseInstance
from .serializers import DatabaseInstanceSerializer


class CollectionHistorySerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = CollectionHistory
        fields = [
            "id", "triggered_by", "status", "started_at", "finished_at",
            "duration_ms", "queries_collected", "rows_written", "error_message",
        ]


class DatabaseInstanceViewSet(viewsets.ModelViewSet):
    """数据库实例 CRUD + 连接测试 + 手动采集 + 采集历史。"""

    queryset = DatabaseInstance.objects.all()
    serializer_class = DatabaseInstanceSerializer

    @action(detail=True, methods=["post"], url_path="test")
    def test_connection(self, request, pk=None):
        instance = self.get_object()
        password = decrypt(instance.password)

        if instance.db_type == "mysql":
            return self._test_mysql(instance, password)
        elif instance.db_type == "postgresql":
            return self._test_postgresql(instance, password)
        elif instance.db_type == "mongodb":
            return self._test_mongodb(instance, password)
        else:
            return Response(
                {"success": False, "message": f"不支持的数据库类型: {instance.db_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"], url_path="collect")
    def collect_now(self, request, pk=None):
        """手动触发一次数据采集（写入历史，triggered_by=manual）。"""
        from .tasks import _do_collect

        instance = self.get_object()

        if instance.db_type not in ("mysql", "postgresql"):
            return Response(
                {"success": False, "message": f"采集器尚未支持 {instance.db_type}"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        result = _do_collect(instance, triggered_by="manual")

        if "error" in result:
            return Response(
                {"success": False, "message": f"采集失败: {result['error']}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "success": True,
            "message": f"采集完成，写入 {result['rows_written']} 条指标",
            "queries_collected": result["queries_collected"],
            "rows_written": result["rows_written"],
        })

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        """GET /api/instances/<id>/history/?limit=20  查询采集历史。"""
        instance = self.get_object()
        limit = min(int(request.query_params.get("limit", 20)), 200)
        qs = instance.collection_histories.all()[:limit]
        return Response(CollectionHistorySerializer(qs, many=True).data)

    def _test_mysql(self, instance, password):
        import pymysql

        try:
            conn = pymysql.connect(
                host=instance.host,
                port=instance.port,
                user=instance.username,
                password=password,
                connect_timeout=5,
            )
            cur = conn.cursor()
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()[0]

            cur.execute("SELECT @@performance_schema")
            ps_enabled = cur.fetchone()[0]

            cur.close()
            conn.close()

            if not ps_enabled:
                return Response({
                    "success": False,
                    "message": "performance_schema 未启用，无法采集慢查询数据",
                    "version": version,
                })

            return Response({
                "success": True,
                "message": "MySQL 连接成功 (performance_schema 已启用)",
                "version": version,
            })
        except Exception as e:
            return Response({"success": False, "message": f"连接失败: {e}"})

    def _test_postgresql(self, instance, password):
        import psycopg2
        try:
            conn = psycopg2.connect(
                host=instance.host,
                port=instance.port,
                user=instance.username,
                password=password,
                connect_timeout=5,
            )
            cur = conn.cursor()
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements'")
            has_ext = cur.fetchone()[0] > 0
            cur.close()
            conn.close()

            if not has_ext:
                return Response({
                    "success": False,
                    "message": "pg_stat_statements 扩展未安装，请执行: CREATE EXTENSION pg_stat_statements",
                    "version": version,
                })
            return Response({
                "success": True,
                "message": "PostgreSQL 连接成功 (pg_stat_statements 已安装)",
                "version": version,
            })
        except Exception as e:
            return Response({"success": False, "message": f"连接失败: {e}"})

    def _test_mongodb(self, instance, password):
        return Response({
            "success": False,
            "message": "MongoDB 采集器尚未实现 (P5 阶段)",
        }, status=status.HTTP_501_NOT_IMPLEMENTED)


class SchedulerStatusView(APIView):
    """GET /api/collector/scheduler/status/  查看调度器运行状态。"""

    def get(self, request):
        from .scheduler import registry
        return Response({"schedulers": registry.status()})

