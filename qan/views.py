from rest_framework.response import Response
from rest_framework.views import APIView

from . import services


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

        queries = services.get_top_queries(service, period, sort_by, limit, search, schema)
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


class OverviewView(APIView):
    """GET /api/qan/overview/?service=xxx&period=1h"""

    def get(self, request):
        service = request.query_params.get("service")
        if not service:
            return Response({"error": "请指定 ?service= 参数"}, status=400)

        period = request.query_params.get("period", "1h")
        overview = services.get_overview(service, period)
        return Response({"service": service, "period": period, "overview": overview})
