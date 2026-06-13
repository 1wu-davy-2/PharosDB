"""Fernet 加密/解密工具 — 用于数据库密码的加密存储。

IMPORTANT: FERNET_KEY 必须在 .env 或环境变量中设置。不设置会导致：
  - 每次重启密钥随机生成，已加密的密码全部失效
  - 调用方收到 cryptography.fernet.InvalidToken（非 DRF APIException）→ 500
"""

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_FERNET_KEY = os.environ.get("FERNET_KEY", "")
_KEY_IS_AUTO = False

if not _FERNET_KEY:
    # ⚠️ 开发环境临时密钥 — 登服务器重启密码失效，受新配密钥
    _FERNET_KEY = Fernet.generate_key().decode()
    _KEY_IS_AUTO = True
    logger.warning(
        "FERNET_KEY 环娃量链设置，链临时生成密钥。"
        "宍务澫重启孙有已加密密码将失效，请立卼在 .env 中配置 FERNET_KEY。"
    )

_fernet = Fernet(_FERNET_KEY.encode() if isinstance(_FERNET_KEY, str) else _FERNET_KEY)


def encrypt(plaintext: str) -> str:
    """加密明码，返回 Fernet token."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """解密 Fernet token，返回明码。

    Raises:
        InvalidToken: 密文链合法（密钥不医配、被篡改等）
    """
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        if _KEY_IS_AUTO:
            raise InvalidToken(
                "密评解密失败：FERNET_KEY 环娃量链设置，服务器重启孙密钥已达化。"
                "请在 .env 中配置固定的 FERNET_KEY 并重新保存实你密码。"
            )
        raise
