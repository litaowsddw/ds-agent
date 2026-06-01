"""安全工具。

提供密码哈希、JWT 签发/验证、API Key 加密/解密等核心安全能力。
"""

import hashlib
import hmac
import os
import base64
import json
import time
from dataclasses import dataclass
from typing import Any

# ──────────────────────────────────────
# 密码哈希
# ──────────────────────────────────────


def hash_password(password: str, salt: bytes | None = None) -> str:
    """使用 PBKDF2 对密码进行哈希。

    参数：
        password: 用户输入的明文密码。
        salt: 可选盐值；为空时自动生成随机盐。
    """

    # password_bytes 是密码的 UTF-8 字节表示，哈希函数只处理字节。
    password_bytes = password.encode("utf-8")

    # final_salt 是本次哈希使用的盐值，防止相同密码得到相同哈希。
    final_salt = salt or os.urandom(16)

    # iterations 是 PBKDF2 迭代次数，MVP 取较保守值，后续可配置。
    iterations = 120_000

    # digest 是密码派生结果，不保存明文密码。
    digest = hashlib.pbkdf2_hmac("sha256", password_bytes, final_salt, iterations)

    return f"pbkdf2_sha256${iterations}${final_salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码是否匹配密码哈希。"""

    try:
        # algorithm 是哈希算法名称，当前只支持 pbkdf2_sha256。
        algorithm, iterations_text, salt_hex, digest_hex = password_hash.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    # iterations 是密码派生迭代次数，来自保存的哈希字符串。
    iterations = int(iterations_text)

    # salt 是保存的盐值。
    salt = bytes.fromhex(salt_hex)

    # expected_digest 是保存的目标摘要。
    expected_digest = bytes.fromhex(digest_hex)

    # actual_digest 是用当前输入密码重新计算出的摘要。
    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)

    return hmac.compare_digest(actual_digest, expected_digest)


# ──────────────────────────────────────
# JWT 签发与验证
# ──────────────────────────────────────

# JWT 密钥，生产环境必须从环境变量读取
_JWT_SECRET = os.getenv("JWT_SECRET", "agentflow-dev-jwt-secret-change-in-production")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRATION_SECONDS = int(os.getenv("JWT_EXPIRATION_SECONDS", "86400"))  # 默认 24 小时


@dataclass(slots=True)
class JWTPayload:
    """JWT 解码后的载荷。"""

    user_id: str
    email: str
    org_id: str | None
    role: str | None
    exp: float
    iat: float


def create_access_token(
    user_id: str,
    email: str,
    org_id: str | None = None,
    role: str | None = None,
    expires_in: int | None = None,
) -> str:
    """签发 JWT Access Token。

    参数：
        user_id: 用户 ID。
        email: 用户邮箱。
        org_id: 当前组织 ID（可选，登录后切换）。
        role: 当前组织角色（可选）。
        expires_in: 过期秒数，默认使用全局配置。

    返回：
        JWT 字符串。
    """
    import hmac as _hmac

    now = time.time()
    exp = now + (expires_in or _JWT_EXPIRATION_SECONDS)

    # header
    header = {"alg": _JWT_ALGORITHM, "typ": "JWT"}

    # payload
    payload = {
        "sub": user_id,
        "email": email,
        "org_id": org_id or "",
        "role": role or "",
        "iat": now,
        "exp": exp,
    }

    # Base64URL 编码
    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")))
    payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")))

    # 签名
    signing_input = f"{header_b64}.{payload_b64}"
    signature = _hmac.new(
        _JWT_SECRET.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_access_token(token: str) -> JWTPayload | None:
    """验证 JWT Token，返回载荷或 None。

    验证步骤：
    1. 拆分 header.payload.signature
    2. 重新计算签名并比对
    3. 检查 exp 过期时间
    4. 解析 payload 字段
    """
    import hmac as _hmac

    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, signature_b64 = parts

    # 验签
    signing_input = f"{header_b64}.{payload_b64}"
    expected_sig = _hmac.new(
        _JWT_SECRET.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    actual_sig = _base64url_decode(signature_b64)

    if not hmac.compare_digest(expected_sig, actual_sig):
        return None

    # 解码 payload
    try:
        payload_json = _base64url_decode(payload_b64).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        return None

    # 过期检查
    exp = payload.get("exp", 0)
    if time.time() > exp:
        return None

    return JWTPayload(
        user_id=payload.get("sub", ""),
        email=payload.get("email", ""),
        org_id=payload.get("org_id") or None,
        role=payload.get("role") or None,
        exp=exp,
        iat=payload.get("iat", 0),
    )


def _base64url_encode(data: bytes | str) -> str:
    """Base64URL 编码（无填充）。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    """Base64URL 解码（自动补填充）。"""
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


# ──────────────────────────────────────
# API Key AES-256 加密
# ──────────────────────────────────────

# 加密主密钥，生产环境必须从环境变量读取（32 字节 = 256 位）
_ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "agentflow-dev-encryption-key-changeme!!")


def encrypt_api_key(plaintext: str) -> str:
    """使用 AES-256-GCM 加密 API Key。

    返回格式：base64(iv:ciphertext:tag)
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        # 降级：如果 cryptography 不可用，用简单 XOR 混淆（仅限开发环境）
        return _simple_obfuscate(plaintext)

    # 派生 256 位密钥
    key = hashlib.sha256(_ENCRYPTION_KEY.encode("utf-8")).digest()

    # 随机 12 字节 IV
    iv = os.urandom(12)

    # AES-GCM 加密
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)

    # 返回 base64(iv + ciphertext)，GCM tag 在 ciphertext 末尾 16 字节
    return base64.b64encode(iv + ciphertext).decode("ascii")


def decrypt_api_key(encrypted: str) -> str:
    """解密 AES-256-GCM 加密的 API Key。"""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return _simple_deobfuscate(encrypted)

    key = hashlib.sha256(_ENCRYPTION_KEY.encode("utf-8")).digest()
    raw = base64.b64decode(encrypted)

    # 前 12 字节是 IV，其余是 ciphertext+tag
    iv = raw[:12]
    ciphertext = raw[12:]

    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, ciphertext, None)
    return plaintext.decode("utf-8")


def mask_api_key(api_key: str) -> str:
    """脱敏 API Key，只保留前缀和后几位。

    示例：sk-proj-secret-key-1234567890abcdef → sk-proj-...cdef
    """
    if len(api_key) <= 8:
        return "***"
    prefix_len = min(8, len(api_key) // 3)
    suffix_len = min(4, len(api_key) // 4)
    return f"{api_key[:prefix_len]}...{api_key[-suffix_len:]}"


# 简单 XOR 混淆（开发环境降级方案，不提供真正安全性）
_OBFUSCATION_SUFFIX = "::obf"


def _simple_obfuscate(plaintext: str) -> str:
    """简单 XOR 混淆（仅限开发环境，不提供真正安全性）。"""
    key_bytes = _ENCRYPTION_KEY.encode("utf-8")
    data_bytes = plaintext.encode("utf-8")
    xored = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data_bytes))
    return base64.b64encode(xored).decode("ascii") + _OBFUSCATION_SUFFIX


def _simple_deobfuscate(encrypted: str) -> str:
    """简单 XOR 反混淆。"""
    if not encrypted.endswith(_OBFUSCATION_SUFFIX):
        # 可能是明文（向后兼容）
        return encrypted
    b64_part = encrypted[: -len(_OBFUSCATION_SUFFIX)]
    key_bytes = _ENCRYPTION_KEY.encode("utf-8")
    xored = base64.b64decode(b64_part)
    data_bytes = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(xored))
    return data_bytes.decode("utf-8")
