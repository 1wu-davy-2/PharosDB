from django.db import migrations

# 精选安全检查规则 — 基于 PMM advisor checks 的 SQL 提取 + 适配
# 字段: (name, display_name, summary, description, family, category, severity, interval, mode, query, threshold, threshold_col)
CHECKS = [
    # ═══ MySQL 安全认证 ═══════════════════════════════════════════
    ("mysql_security_anonymous_user", "MySQL 匿名用户检查",
     "检测是否存在匿名用户", "mysql.user 表中不应存在匿名用户（User=''）",
     "mysql", "security", "error", "standard", "exists",
     "SELECT @@version version, @@hostname service, COUNT(user) found, GROUP_CONCAT(CONCAT(user,'@',host) SEPARATOR '; ') user FROM mysql.user WHERE user LIKE '' GROUP BY version, service", 0, "value"),
    ("mysql_security_user_without_password", "MySQL 无密码用户检查",
     "检测是否存在无密码用户", "任何用户必须设置密码或使用外部认证（auth_socket/pam 除外）",
     "mysql", "security", "critical", "standard", "exists",
     "SELECT @@version version, @@hostname service, COUNT(user) found, GROUP_CONCAT(CONCAT(user,'@',host) SEPARATOR '; ') user FROM mysql.user WHERE authentication_string = '' AND account_locked = 'N' AND plugin NOT IN ('auth_socket','unix_socket','auth_pam','auth_pam_compat','pam','AWSAuthenticationPlugin') GROUP BY version, service", 0, "value"),
    ("mysql_security_root_not_local", "MySQL Root 远程访问",
     "Root 用户可从非本地主机连接", "Root 用户只应允许本地连接（localhost/127.0.0.1/::1）",
     "mysql", "security", "error", "standard", "exists",
     "SELECT @@version version, @@hostname service, GROUP_CONCAT(CONCAT(user,'@',host) SEPARATOR '; ') user_host FROM mysql.user WHERE user = 'root' AND host NOT IN ('localhost','127.0.0.1','::1') HAVING COUNT(*) > 0", 0, "value"),
    ("mysql_security_open_to_world_host", "MySQL 全网开放主机检查",
     "存在使用 '%' 或 '0.0.0.0' 的主机权限", "数据库用户的主机范围不应设置为全网开放",
     "mysql", "security", "error", "standard", "exists",
     "SELECT @@version version, @@hostname service, COUNT(*) found, GROUP_CONCAT(CONCAT(user,'@',host) SEPARATOR '; ') users FROM mysql.user WHERE host IN ('%','0.0.0.0') AND user NOT IN ('root')", 0, "value"),
    ("mysql_security_user_super_not_local", "MySQL 非 Root 超级权限检查",
     "非 Root 账户拥有超级权限（SUPER/ALL PRIVILEGES）", "只有 root 应拥有超级权限",
     "mysql", "security", "warning", "standard", "exists",
     "SELECT @@version version, @@hostname service, COUNT(*) found, GROUP_CONCAT(CONCAT(grantee,'@',host) SEPARATOR '; ') grantees FROM information_schema.user_privileges WHERE privilege_type IN ('SUPER','ALL PRIVILEGES','FILE','SHUTDOWN') AND grantee NOT LIKE '%root%' AND grantee NOT LIKE '%pmm%' AND grantee NOT LIKE '%mariadb%'", 0, "value"),
    ("mysql_security_user_ssl", "MySQL SSL 连接检查",
     "用户未启用 SSL/TLS 加密连接", "所有用户应尽量使用 SSL 连接",
     "mysql", "security", "info", "rare", "exists",
     "SELECT @@version version, @@hostname service, COUNT(*) found FROM mysql.user WHERE ssl_type = '' AND user NOT IN ('mariadb.sys','mysql.sys','pmm')", 0, "value"),

    # ═══ MySQL 配置安全 ═══════════════════════════════════════════
    ("mysql_security_require_secure_transport", "MySQL 明文传输检查",
     "服务器允许非加密远程连接", "生产环境应启用 require_secure_transport=ON",
     "mysql", "security", "warning", "standard", "exists",
     "SELECT @@version version, @@hostname service, @@require_secure_transport secure_transport HAVING secure_transport = 0", 0, "value"),
    ("mysql_security_password_policy", "MySQL 密码策略检查",
     "密码验证插件未启用或策略过弱", "密码策略应为 STRONG 或至少 MEDIUM",
     "mysql", "security", "warning", "standard", "exists",
     "SELECT @@version version, @@hostname service, @@validate_password_policy policy, @@validate_password_length min_length HAVING policy = 'LOW' OR min_length < 8", 0, "value"),
    ("mysql_security_password_lifetime", "MySQL 密码过期策略",
     "未设置密码过期时间", "应设置 default_password_lifetime 启用密码定期轮换",
     "mysql", "security", "info", "rare", "exists",
     "SELECT @@version version, @@hostname service, @@default_password_lifetime days HAVING days = 0", 0, "value"),
    ("mysql_security_local_infile", "MySQL LOAD DATA LOCAL 检查",
     "local_infile 已启用，存在数据泄露风险", "生产环境应禁用 local_infile",
     "mysql", "security", "error", "standard", "exists",
     "SELECT @@version version, @@hostname service, @@local_infile local_infile HAVING local_infile = 1", 0, "value"),

    # ═══ PostgreSQL 安全认证 ══════════════════════════════════════
    ("pg_security_super_role", "PG 超级用户检查",
     "非 postgres 用户拥有超级用户角色", "仅 postgres 应拥有 SUPERUSER 权限",
     "postgresql", "security", "error", "standard", "exists",
     "SELECT version() version, count(*) found, string_agg(rolname,', ') superusers FROM pg_roles WHERE rolsuper = true AND rolname NOT IN ('postgres','pmm') HAVING count(*) > 0", 0, "value"),
    ("pg_security_no_password", "PG 无密码认证检查",
     "pg_hba.conf 中存在 trust 认证方式", "trust 认证方式允许无密码连接，生产环境应使用 scram-sha-256 或 md5",
     "postgresql", "security", "critical", "standard", "exists",
     "SELECT version() version, count(*) found FROM pg_hba_file_rules WHERE auth_method = 'trust' AND database NOT IN ('template0','template1')", 0, "value"),
    ("pg_security_public_schema", "PG Public Schema 权限检查",
     "所有用户默认可以创建对象在 public schema", "建议撤销 public schema 的 CREATE 权限",
     "postgresql", "security", "warning", "standard", "exists",
     "SELECT version() version, count(*) found FROM information_schema.role_table_grants WHERE table_schema = 'public' AND privilege_type = 'INSERT' AND grantee = 'PUBLIC' HAVING count(*) > 0 LIMIT 1", 0, "value"),
    ("pg_security_ssl", "PG SSL 连接检查",
     "PostgreSQL 未强制 SSL 连接", "建议在 postgresql.conf 中设置 ssl=on",
     "postgresql", "security", "warning", "standard", "exists",
     "SELECT version() version, current_setting('ssl') ssl HAVING ssl = 'off'", 0, "value"),
    ("pg_security_cve", "PG CVE 版本检查",
     "PostgreSQL 版本过旧可能存在已知漏洞", "定期检查并升级到最新 minor 版本",
     "postgresql", "security", "warning", "rare", "exists",
     "SELECT version() version, regexp_replace(current_setting('server_version'), E'\\\\.[0-9]+$','') major_version WHERE current_setting('server_version_num')::int < 160000", 0, "value"),

    # ═══ 通用配置 ═══════════════════════════════════════════
    ("generic_connection_count", "数据库连接数阈值检查",
     "当前活跃连接数超过最大连接数的 80%", "接近连接池上限可能导致新连接被拒绝",
     "mysql", "performance", "warning", "frequent", "exists",
     "SELECT @@version version, @@hostname service, @@max_connections max_conn, COUNT(*) current_conn FROM information_schema.processlist HAVING current_conn > @@max_connections * 0.8", 0, "value"),
    ("generic_binary_log", "MySQL Binlog 检查",
     "未开启二进制日志", "binlog 对于时间点恢复和复制至关重要",
     "mysql", "configuration", "warning", "standard", "exists",
     "SELECT @@version version, @@hostname service, @@log_bin log_bin, @@expire_logs_days expire_days HAVING log_bin = 0", 0, "value"),
]


def seed_checks(apps, schema_editor):
    AdvisorCheck = apps.get_model("advisor", "AdvisorCheck")
    for (name, display, summary, desc, family, cat, sev,
         interval, mode, query, threshold, threshold_col) in CHECKS:
        AdvisorCheck.objects.get_or_create(
            name=name,
            defaults={
                "display_name": display,
                "summary": summary,
                "description": desc,
                "family": family,
                "category": cat,
                "severity": sev,
                "interval": interval,
                "mode": mode,
                "query": query,
                "threshold": threshold,
                "threshold_column": threshold_col,
                "enabled": True,
            },
        )


def unseed_checks(apps, schema_editor):
    AdvisorCheck = apps.get_model("advisor", "AdvisorCheck")
    AdvisorCheck.objects.filter(name__in=[c[0] for c in CHECKS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("advisor", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(seed_checks, unseed_checks),
    ]
