from django.urls import path

from .views import LockHistoryView, LockTopologyView

app_name = "locks"

urlpatterns = [
    path("topology/", LockTopologyView.as_view(), name="topology"),
    path("history/",  LockHistoryView.as_view(),  name="history"),
]
