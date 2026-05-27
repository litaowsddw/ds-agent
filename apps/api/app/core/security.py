"""安全工具。

MVP 阶段先提供密码哈希和校验能力。后续接入正式登录后，会继续补充 JWT、
API Key、密钥加密和组织级 Secret Manager。
"""

import hashlib
import hmac
import os


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
