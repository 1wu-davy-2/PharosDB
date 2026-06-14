"""安全巡检 URL 路由。"""

from django.urls import path

from . import views

app_name = "advisor"

urlpatterns = [
    # 巡检规则
    path("advisor/checks/",                views.CheckListView.as_view(),         name="checks"),
    path("advisor/checks/toggle/",         views.ToggleCheckView.as_view(),       name="toggle"),
    path("advisor/checks/<int:pk>/targeting/", views.CheckTargetingView.as_view(), name="check-targeting"),
    # 巡检发现
    path("advisor/findings/",              views.FindingListView.as_view(),       name="findings"),
    path("advisor/summary/",               views.SummaryView.as_view(),           name="summary"),
    # 执行巡检
    path("advisor/run/",                   views.RunCheckView.as_view(),          name="run"),
    # 实例分组
    path("advisor/groups/",                views.GroupListView.as_view(),         name="groups"),
    path("advisor/groups/<int:pk>/",       views.GroupDetailView.as_view(),       name="group-detail"),
    # 调度器
    path("advisor/scheduler/status/",      views.SchedulerStatusView.as_view(),   name="scheduler-status"),
    path("advisor/scheduler/toggle/",      views.SchedulerToggleView.as_view(),   name="scheduler-toggle"),
]
