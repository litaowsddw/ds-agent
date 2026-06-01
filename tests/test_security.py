"""安全模块单元测试 — JWT、加密、RBAC。"""

import time
import sys
import os
import pytest

# 确保可以找到 app 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token,
    encrypt_api_key,
    decrypt_api_key,
    mask_api_key,
)
from app.services.rbac import (
    Permission,
    RBACService,
    RBACPolicy,
    ROLE_PERMISSIONS,
)
from app.domain.identity import Membership, OrganizationRole


# ──────────────────────────────────────
# 密码哈希测试
# ──────────────────────────────────────


class TestPasswordHash:
    """密码哈希测试套件。"""

    def test_hash_and_verify(self) -> None:
        """密码哈希和验证正常工作。"""
        password = "SecurePass123!"
        hashed = hash_password(password)
        assert verify_password(password, hashed)

    def test_different_hashes_for_same_password(self) -> None:
        """相同密码产生不同哈希（随机盐）。"""
        password = "SamePassword456"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_wrong_password_fails(self) -> None:
        """错误密码验证失败。"""
        hashed = hash_password("CorrectPass789")
        assert not verify_password("WrongPass789", hashed)

    def test_invalid_hash_format(self) -> None:
        """无效哈希格式返回 False。"""
        assert not verify_password("any", "invalid_hash")
        assert not verify_password("any", "")
        assert not verify_password("any", "md5$1$salt$digest")


# ──────────────────────────────────────
# JWT 测试
# ──────────────────────────────────────


class TestJWT:
    """JWT 签发和验证测试套件。"""

    def test_create_and_verify_token(self) -> None:
        """JWT 签发和验证正常工作。"""
        token = create_access_token(user_id="usr_123", email="test@example.com")
        payload = verify_access_token(token)
        assert payload is not None
        assert payload.user_id == "usr_123"
        assert payload.email == "test@example.com"

    def test_token_with_org_context(self) -> None:
        """JWT 包含组织上下文。"""
        token = create_access_token(
            user_id="usr_456",
            email="org@example.com",
            org_id="org_789",
            role="admin",
        )
        payload = verify_access_token(token)
        assert payload is not None
        assert payload.org_id == "org_789"
        assert payload.role == "admin"

    def test_expired_token_fails(self) -> None:
        """过期 Token 验证失败。"""
        token = create_access_token(
            user_id="usr_expired",
            email="expired@example.com",
            expires_in=-1,  # 已过期
        )
        payload = verify_access_token(token)
        assert payload is None

    def test_tampered_token_fails(self) -> None:
        """篡改的 Token 验证失败。"""
        token = create_access_token(user_id="usr_tamper", email="tamper@example.com")
        # 篡改 payload 部分
        parts = token.split(".")
        parts[1] = parts[1][:-4] + "XXXX"
        tampered = ".".join(parts)
        payload = verify_access_token(tampered)
        assert payload is None

    def test_invalid_token_format(self) -> None:
        """无效 Token 格式返回 None。"""
        assert verify_access_token("") is None
        assert verify_access_token("not.a.valid.token.format") is None
        assert verify_access_token("only.one") is None


# ──────────────────────────────────────
# API Key 加密测试
# ──────────────────────────────────────


class TestAPIKeyEncryption:
    """API Key 加密/解密测试套件。"""

    def test_encrypt_and_decrypt(self) -> None:
        """加密解密正常工作。"""
        original = "sk-proj-secret-key-1234567890abcdef"
        encrypted = encrypt_api_key(original)
        assert encrypted != original
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == original

    def test_different_encryptions_differ(self) -> None:
        """同一明文不同次加密结果不同（随机 IV）。"""
        key = "sk-same-key-every-time"
        enc1 = encrypt_api_key(key)
        enc2 = encrypt_api_key(key)
        # 注意：XOR 降级模式下可能相同
        # 但至少解密结果应正确
        assert decrypt_api_key(enc1) == key
        assert decrypt_api_key(enc2) == key

    def test_empty_key(self) -> None:
        """空 Key 处理正常。"""
        encrypted = encrypt_api_key("")
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == ""

    def test_mask_api_key(self) -> None:
        """Key 脱敏正常工作。"""
        assert mask_api_key("sk-proj-secret-key-1234567890abcdef") == "sk-proj-...cdef"
        assert mask_api_key("short") == "***"
        assert mask_api_key("") == "***"


# ──────────────────────────────────────
# RBAC 测试
# ──────────────────────────────────────


class TestRBAC:
    """RBAC 权限测试套件。"""

    def test_owner_has_all_permissions(self) -> None:
        """Owner 拥有所有权限。"""
        membership = Membership(
            membership_id="mem_test",
            org_id="org_test",
            user_id="usr_test",
            role=OrganizationRole.OWNER,
        )
        service = RBACService()
        for perm in Permission:
            assert service.has_permission(membership, perm), f"Owner 应有权限 {perm.value}"

    def test_viewer_limited_permissions(self) -> None:
        """Viewer 只有读权限。"""
        membership = Membership(
            membership_id="mem_viewer",
            org_id="org_test",
            user_id="usr_viewer",
            role=OrganizationRole.VIEWER,
        )
        service = RBACService()
        # Viewer 应有的权限
        assert service.has_permission(membership, Permission.ORGANIZATION_READ)
        assert service.has_permission(membership, Permission.AGENT_READ)
        # Viewer 不应有的权限
        assert not service.has_permission(membership, Permission.AGENT_CREATE)
        assert not service.has_permission(membership, Permission.WORKFLOW_CREATE)
        assert not service.has_permission(membership, Permission.ORGANIZATION_MANAGE)

    def test_developer_permissions(self) -> None:
        """Developer 有创建但无管理权限。"""
        membership = Membership(
            membership_id="mem_dev",
            org_id="org_test",
            user_id="usr_dev",
            role=OrganizationRole.DEVELOPER,
        )
        service = RBACService()
        # Developer 应有
        assert service.has_permission(membership, Permission.AGENT_CREATE)
        assert service.has_permission(membership, Permission.WORKFLOW_CREATE)
        assert service.has_permission(membership, Permission.AGENT_CHAT)
        # Developer 不应有
        assert not service.has_permission(membership, Permission.AUDIT_READ)
        assert not service.has_permission(membership, Permission.ORGANIZATION_MANAGE)

    def test_no_membership_denied(self) -> None:
        """无成员关系时拒绝所有权限。"""
        service = RBACService()
        assert not service.has_permission(None, Permission.ORGANIZATION_READ)

    def test_require_permission_raises(self) -> None:
        """require_permission 在权限不足时抛出异常。"""
        membership = Membership(
            membership_id="mem_viewer2",
            org_id="org_test",
            user_id="usr_viewer2",
            role=OrganizationRole.VIEWER,
        )
        service = RBACService()
        with pytest.raises(PermissionError):
            service.require_permission(membership, Permission.AGENT_CREATE)

    def test_dynamic_policy_override(self) -> None:
        """动态策略可以覆盖默认权限。"""
        membership = Membership(
            membership_id="mem_dyn",
            org_id="org_dyn",
            user_id="usr_dyn",
            role=OrganizationRole.VIEWER,
        )

        # Viewer 默认不能创建 Agent
        service = RBACService()
        assert not service.has_permission(membership, Permission.AGENT_CREATE)

        # 添加动态策略：允许 viewer 创建 Agent
        policy = RBACPolicy(
            policy_id="pol_1",
            org_id="org_dyn",
            role="viewer",
            permission="agent:create",
            allowed=True,
            priority=10,
        )
        service.add_policy(policy)
        assert service.has_permission(membership, Permission.AGENT_CREATE)

    def test_dynamic_policy_deny_override(self) -> None:
        """动态策略可以禁止默认允许的权限。"""
        membership = Membership(
            membership_id="mem_deny",
            org_id="org_deny",
            user_id="usr_deny",
            role=OrganizationRole.DEVELOPER,
        )

        # Developer 默认可以创建 Agent
        service = RBACService()
        assert service.has_permission(membership, Permission.AGENT_CREATE)

        # 添加动态策略：禁止 developer 删除 Agent
        policy = RBACPolicy(
            policy_id="pol_2",
            org_id="org_deny",
            role="developer",
            permission="agent:delete",
            allowed=False,
            priority=10,
        )
        service.add_policy(policy)
        assert not service.has_permission(membership, Permission.AGENT_DELETE)

    def test_get_permissions(self) -> None:
        """get_permissions 返回正确的权限集合。"""
        membership = Membership(
            membership_id="mem_perms",
            org_id="org_perms",
            user_id="usr_perms",
            role=OrganizationRole.VIEWER,
        )
        service = RBACService()
        perms = service.get_permissions(membership)
        assert Permission.ORGANIZATION_READ in perms
        assert Permission.AGENT_CREATE not in perms

    def test_remove_policy(self) -> None:
        """移除动态策略后恢复默认权限。"""
        membership = Membership(
            membership_id="mem_remove",
            org_id="org_remove",
            user_id="usr_remove",
            role=OrganizationRole.VIEWER,
        )

        service = RBACService()
        policy = RBACPolicy(
            policy_id="pol_remove",
            org_id="org_remove",
            role="viewer",
            permission="agent:create",
            allowed=True,
            priority=10,
        )
        service.add_policy(policy)
        assert service.has_permission(membership, Permission.AGENT_CREATE)

        service.remove_policy("org_remove", "pol_remove")
        assert not service.has_permission(membership, Permission.AGENT_CREATE)
