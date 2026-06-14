"""Accounts models — login attempt tracking for brute-force protection."""

from django.db import models


class LoginAttempt(models.Model):
    """记录每次登录尝试，用于检测暴力破解并锁定账号。

    锁定策略：同一用户名 + IP 在时间窗口内连续失败 N 次后拒绝后续尝试。
    N（默认 5）和窗口（默认 15 分钟）可通过 SystemConfig 配置。
    """

    username = models.CharField("用户名", max_length=150, db_index=True)
    ip_address = models.CharField("客户端 IP", max_length=64, default="0.0.0.0")
    success = models.BooleanField("是否成功", default=False)
    attempted_at = models.DateTimeField("尝试时间", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "accounts_login_attempt"
        verbose_name = "登录尝试记录"
        verbose_name_plural = verbose_name
        ordering = ["-attempted_at"]

    def __str__(self):
        status = "成功" if self.success else "失败"
        return f"{self.username} @ {self.ip_address} — {status}"
