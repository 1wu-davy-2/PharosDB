from django.urls import path

from . import views

app_name = "qan"

urlpatterns = [
    path("top-queries/", views.TopQueriesView.as_view(), name="top_queries"),
    path("overview/", views.OverviewView.as_view(), name="overview"),
    path("query/<str:queryid>/", views.QueryDetailView.as_view(), name="query_detail"),
    path("query/<str:queryid>/trend/", views.QueryTrendView.as_view(), name="query_trend"),
]
