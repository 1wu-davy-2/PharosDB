"""安全巡检 URL 路由。"""
from django.urls import path

from . import views

app_name = "advisor"

urlpatterns = [
    path("advisor/checks/",       views.CheckListView.as_view(),     name="checks"),
    path("advisor/checks/toggle/", views.ToggleCheckView.as_view(),  name="toggle"),
    path("advisor/findings/",    views.FindingListView.as_view(),    name="findings"),
    path("advisor/summary/",     views.SummaryView.as_view(),       name="summary"),
    path("advisor/run/",         views.RunCheckView.as_view(),      name="run"),
]
