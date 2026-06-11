"""Fernet 加密/解密工具 — 用于数据库密码的加密存储。"""

import os

from cryptography.fernet import Fernet
from django.conf import settings

_FERNET_KEY = os.environ.get("FERNET_KEY", "")

if not _FERNET_KEY:
    # 开发环境自动生成密钥 (生产环境必须设置 FERNET_KEY 环境变量)
    _FERNET_KEY = Fernet.generate_key().decode()
    os.environ["FERNET_KEY"] = _FERNET_KEY

_fernet = Fernet(_FERNET_KEY.encode() if isinstance(_FERNET_KEY, str) else _FERNET_KEY)


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
