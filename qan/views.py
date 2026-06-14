from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasPermission
from . import cross_services, plan_services, services


class TopQueriesView(APIView):
    """GET /api/qan/top-queries/?service=xxx&period=1h&sort=m_query_time_sum&limit=20&search=xxx&schema=xxx"""

    def get(self, request):
        service = request.query_params.get("service")
        if not service:
            service_list = services.get_service_list()
            return Response({"services": service_list, "message": "请指定 ?service= 参数"})

        period = request.query_params.get("period", "1h")
        sort_by = request.query_params.get("sort", "m_query_time_sum")
        limit = int(request.query_params.get("limit", 20))
        search = request.query_params.get("search", "")
        schema = request.query_params.get("schema", "")
        order = request.query_params.get("order", "DESC")

        queries = services.get_top_queries(service, period, sort_by, limit, search, schema, order)
        return Response({"service": service, "period": period, "queries": queries})


class QueryDetailView(APIView):
    """GET /api/qan/query/<queryid>/?service=xxx&period=1h"""

    def get(self, request, queryid):
        service = request.query_params.get("service")
        if not service:
            return Response({"error": "请指定 ?service= 参数"}, status=400)

        period = request.query_params.get("period", "1h")
        detail = services.get_query_detail(queryid, service, period)

        if detail is None:
            return Response({"error": "未找到该查询"}, status=404)

        return Response(detail)


class QueryTrendView(APIView):
    """GET /api/qan/query/<queryid>/trend/?service=xxx&hours=24"""

    def get(self, request, queryid):
        service = request.query_params.get("service")
        if not service:
            return Response({"error": "请指定 ?service= 参数"}, status=400)

        hours = int(request.query_params.get("hours", 24))
        trend = services.get_query_trend(queryid, service, hours)
        return Response({"queryid": queryid, "service": service, "trend": trend})


class IndexAnalysisView(APIView):
    """GET /api/qan/index-analysis/?service=xxx

    返回未使用索引 + 缺失索引推荐列表。
    """

    def get(self, request):
        service = request.query_params.get("service")
        if not service:
            return Response({"error": "请指定 ?service= 参数"}, status=400)

        result = services.index_analysis(service)
        return Response(result)


class OverviewView(APIView):
    """GET /api/qan/overview/?service=xxx&period=1h"""

    def get(self, request):
        service = request.query_params.get("service")
        if not service:
            return Response({"error": "请指定 ?service= 参数"}, status=400)

        period = request.query_params.get("period", "1h")
        overview = services.get_overview(service, period)
        return Response({"service": service, "period": period, "overview": overview})


# ═══ 执行计划 API ═══════════════════════════════════════════════════


class PlanListView(APIView):
    """GET /api/qan/plans/?fingerprint=xxx&service=xxx&limit=50"""

    def get(self, request):
        fp = request.query_params.get("fingerprint")
        if not fp:
            return Response({"error": "请指定 ?fingerprint= 参数"}, status=400)
        svc = request.query_params.get("service")
        limit = int(request.query_params.get("limit", 50))
        plans = plan_services.get_plan_list(fp, svc, limit)
        return Response({"fingerprint": fp, "plans": plans})


class PlanDetailView(APIView):
    """GET /api/qan/plans/<plan_id>/"""

    def get(self, request, plan_id):
        plan = plan_services.get_plan_detail(plan_id)
        if plan is None:
            return Response({"error": "未找到该执行计划"}, status=404)
        return Response(plan)


class PlanCompareView(APIView):
    """GET /api/qan/plans/compare/?a=<plan_id>&b=<plan_id>"""

    def get(self, request):
        a = request.query_params.get("a")
        b = request.query_params.get("b")
        if not a or not b:
            return Response({"error": "请指定 ?a=&b= 两个计划 ID"}, status=400)
        result = plan_services.compare_plans(a, b)
        if result is None:
            return Response({"error": "计划不存在"}, status=404)
        return Response(result)


class ManualExplainView(APIView):
    """POST /api/qan/explain/"""

    permission_classes = [HasPermission]
    required_permission = "qan:explain"

    def post(self, request):
        sql_text = (request.data.get("sql") or "").strip()
        digest = (request.data.get("digest") or "").strip()
        service = (request.data.get("service") or "").strip()

        if not sql_text and not (digest and service):
            return Response(
                {"error": "请提供 sql 或 (digest + service)"},
                status=400,
            )

        # 从数据库实例获取连接信息
        from collector.models import DatabaseInstance
        from collector.crypto import decrypt

        try:
            inst = DatabaseInstance.objects.get(name=service)
        except DatabaseInstance.DoesNotExist:
            return Response({"error": f"实例 {service} 不存在"}, status=404)

        try:
            password = decrypt(inst.password)
        except Exception as e:
            return Response(
                {"error": f"密码解密失败: {e}. 请检查 FERNET_KEY 配置或重新保存实例密码。"},
                status=500,
            )

        try:
            if inst.db_type == "mysql":
                return self._explain_mysql(inst, password, sql_text, digest)
            elif inst.db_type == "postgresql":
                return self._explain_postgresql(inst, password, sql_text)
            return Response(
                {"error": f"不支持的数据库类型: {inst.db_type}"},
                status=400,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=500)

    def _explain_mysql(self, inst, password, sql_text, digest):
        import pymysql

        conn = None
        cur = None
        try:
            conn = pymysql.connect(
                host=inst.host, port=inst.port,
                user=inst.username, password=password,
                connect_timeout=5, charset="utf8mb4",
            )
        except Exception as e:
            return Response({"error": f"连接失败: {e}"}, status=500)

        try:
            cur = conn.cursor(pymysql.cursors.DictCursor)

            # 如果没给 sql_text，从 history_long 查
            if not sql_text and digest:
                cur.execute(
                    "SELECT SQL_TEXT FROM performance_schema.events_statements_history_long "
                    "WHERE DIGEST = %s AND SQL_TEXT IS NOT NULL LIMIT 1",
                    (digest,),
                )
                row = cur.fetchone()
                if row:
                    sql_text = row.get("SQL_TEXT", "")[:8192]
                if not sql_text:
                    cur.close()
                    conn.close()
                    return Response({"error": "history_long 中未找到该 digest 的 SQL"}, status=404)

            # 执行 EXPLAIN
            try:
                cur.execute("SET STATEMENT max_statement_time=3 FOR EXPLAIN FORMAT=JSON " + sql_text)
            except Exception:
                cur.execute("EXPLAIN FORMAT=JSON " + sql_text)
            plan = cur.fetchone()

            if not plan:
                return Response({"error": "EXPLAIN 返回空"}, status=500)

            import json as _json
            plan_str = plan.get("EXPLAIN", "") if isinstance(plan, dict) else str(plan)
            plan_dict = _json.loads(plan_str) if isinstance(plan_str, str) else plan_str

            from collector.collectors.mysql import normalize_plan_summary
            summary = normalize_plan_summary(plan_dict)
            import hashlib
            plan_hash = hashlib.md5(summary.encode()).hexdigest()

            return Response({
                "plan_json": plan_dict,
                "plan_summary": summary,
                "plan_hash": plan_hash,
                "sql_text": sql_text,
            })
        except Exception as e:
            return Response({"error": str(e)}, status=500)
        finally:
            if cur is not None:
                cur.close()
            if conn is not None:
                conn.close()

    def _explain_postgresql(self, inst, password, sql_text):
        import psycopg2

        conn = None
        cur = None
        try:
            conn = psycopg2.connect(
                host=inst.host, port=inst.port,
                user=inst.username, password=password,
                connect_timeout=5,
            )
        except Exception as e:
            return Response({"error": f"连接失败: {e}"}, status=500)

        try:
            cur = conn.cursor()
            cur.execute("EXPLAIN (FORMAT JSON) " + sql_text)
            plan = cur.fetchone()
            return Response({"plan_json": plan[0] if plan else None})
        except Exception as e:
            return Response({"error": str(e)}, status=500)
        finally:
            if cur is not None:
                cur.close()
            if conn is not None:
                conn.close()


# ═══ 跨节点诊断 API ═════════════════════════════════════════════


class CrossNodeCorrelationView(APIView):
    """GET /api/qan/cross-node/correlation/

    参数:
      ?cluster=galera-prod-01     (必填：集群名称)
      &start=2026-06-14T00:00:00  (ISO 时间)
      &end=2026-06-14T01:00:00
      &min_confidence=60          (默认 60)
    """

    def get(self, request):
        cluster = request.query_params.get("cluster", "").strip()
        if not cluster:
            from collector.models import DatabaseInstance
            clusters = sorted(set(
                DatabaseInstance.objects.exclude(cluster="")
                .values_list("cluster", flat=True)
            ))
            return Response({
                "clusters": clusters,
                "message": "请指定 ?cluster= 参数",
            })

        start = request.query_params.get("start", "")
        end = request.query_params.get("end", "")
        min_conf = int(request.query_params.get("min_confidence", 60))

        if not start or not end:
            return Response({"error": "请指定 ?start= & ?end= ISO 时间"}, status=400)

        result = cross_services.get_cross_node_correlations(
            cluster, start, end, min_confidence=min_conf
        )
        return Response(result)


class CrossNodeLockView(APIView):
    """GET /api/qan/cross-node/locks/

    参数:
      ?cluster=galera-prod-01
      &start=2026-06-14T00:00:00
      &end=2026-06-14T01:00:00
    """

    def get(self, request):
        cluster = request.query_params.get("cluster", "").strip()
        if not cluster:
            from collector.models import DatabaseInstance
            clusters = sorted(set(
                DatabaseInstance.objects.exclude(cluster="")
                .values_list("cluster", flat=True)
            ))
            return Response({
                "clusters": clusters,
                "message": "请指定 ?cluster= 参数",
            })

        start = request.query_params.get("start", "")
        end = request.query_params.get("end", "")

        if not start or not end:
            return Response({"error": "请指定 ?start= & ?end= ISO 时间"}, status=400)

        result = cross_services.get_cross_node_locks(cluster, start, end)
        return Response(result)
