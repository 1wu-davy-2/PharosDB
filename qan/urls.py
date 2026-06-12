from django.urls import path

from . import views

app_name = "qan"

urlpatterns = [
    path("top-queries/", views.TopQueriesView.as_view(), name="top_queries"),
    path("overview/", views.OverviewView.as_view(), name="overview"),
    path("query/<str:queryid>/", views.QueryDetailView.as_view(), name="query_detail"),
    path("query/<str:queryid>/trend/", views.QueryTrendView.as_view(), name="query_trend"),
    # 执行计划
    path("plans/", views.PlanListView.as_view(), name="plan_list"),
    path("plans/compare/", views.PlanCompareView.as_view(), name="plan_compare"),
    path("plans/<str:plan_id>/", views.PlanDetailView.as_view(), name="plan_detail"),
    path("explain/", views.ManualExplainView.as_view(), name="manual_explain"),
]
