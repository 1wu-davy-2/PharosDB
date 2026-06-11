from datetime import timezone as tz

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .clickhouse import ClickHouseWriter
from .collectors.mysql import MySQLCollector
from .crypto import decrypt
from .models import DatabaseInstance
from .serializers import DatabaseInstanceSerializer


class DatabaseInstanceViewSet(viewsets.ModelViewSet):
    """数据库实例 CRUD + 连接测试 + 手动采集。"""

    queryset = DatabaseInstance.objects.all()
    serializer_class = DatabaseInstanceSerializer

    @action(detail=True, methods=["post"], url_path="test")
    def test_connection(self, request, pk=None):
        """测试到目标数据库的连接。"""
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
        """手动触发一次数据采集。"""
        instance = self.get_object()

        if instance.db_type != "mysql":
            return Response(
                {"success": False, "message": f"采集器尚未支持 {instance.db_type}"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        try:
            collector = MySQLCollector(instance)
            rows = collector.run()

            if rows:
                writer = ClickHouseWriter()
                count = writer.write_metrics(rows)
            else:
                count = 0

            from django.utils import timezone
            instance.last_collected_at = timezone.now()
            instance.save(update_fields=["last_collected_at"])

            return Response({
                "success": True,
                "message": f"采集完成，写入 {count} 条指标",
                "queries_collected": len(rows),
                "rows_written": count,
            })
        except Exception as e:
            return Response(
                {"success": False, "message": f"采集失败: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

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

            # 检查 performance_schema 是否启用
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
                "message": f"MySQL 连接成功 (performance_schema 已启用)",
                "version": version,
            })
        except Exception as e:
            return Response({
                "success": False,
                "message": f"连接失败: {e}",
            })

    def _test_postgresql(self, instance, password):
        return Response({
            "success": False,
            "message": "PostgreSQL 采集器尚未实现 (P5 阶段)",
        }, status=status.HTTP_501_NOT_IMPLEMENTED)

    def _test_mongodb(self, instance, password):
        return Response({
            "success": False,
            "message": "MongoDB 采集器尚未实现 (P5 阶段)",
        }, status=status.HTTP_501_NOT_IMPLEMENTED)
