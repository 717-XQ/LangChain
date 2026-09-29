# -*- coding: utf-8 -*-
"""
tool_permission.py - 工具权限统一管理系统
=============================================
功能：
  1. 定义工具风险等级（READ / SANDBOX / DANGEROUS）
  2. 所有Tool注册时声明permission属性
  3. Agent执行工具前统一检查权限
  4. DANGEROUS级工具触发Human-in-the-loop审批
  5. 权限检查日志记录（审计追踪）

权限等级定义：
  READ      - 只读操作，无副作用（搜索、计算、SQL SELECT、RAG、记忆读取）
  SANDBOX   - 受控环境中执行，有潜在风险但在隔离环境中（Python代码执行）
  DANGEROUS - 有不可逆副作用，必须人工确认（SQL DELETE/UPDATE、文件删除、系统命令）

执行策略：
  READ      → 自动执行，仅记录日志
  SANDBOX   → 受控环境执行（子进程隔离 + timeout + 资源限制）
  DANGEROUS → 暂停执行，等待人工确认（Human-in-the-loop）
"""

import time
from enum import Enum
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from loguru import logger


class RiskLevel(Enum):
    """工具风险等级"""
    READ = "READ"           # 只读，无副作用
    SANDBOX = "SANDBOX"     # 受控环境执行
    DANGEROUS = "DANGEROUS"  # 高风险，需人工确认


# 风险等级描述
RISK_DESCRIPTIONS = {
    RiskLevel.READ: "只读操作，无副作用，可安全自动执行",
    RiskLevel.SANDBOX: "在隔离环境中执行，有潜在风险但受控制",
    RiskLevel.DANGEROUS: "有不可逆副作用，必须人工确认后才能执行",
}

# 执行策略描述
EXECUTION_STRATEGIES = {
    RiskLevel.READ: "自动执行，仅记录审计日志",
    RiskLevel.SANDBOX: "子进程隔离执行，设置timeout和资源限制",
    RiskLevel.DANGEROUS: "暂停执行，触发Human-in-the-loop等待人工确认",
}


@dataclass
class PermissionCheckResult:
    """权限检查结果"""
    allowed: bool                    # 是否允许执行
    risk_level: RiskLevel            # 风险等级
    requires_approval: bool          # 是否需要人工审批
    reason: str = ""                 # 原因说明
    approval_id: Optional[str] = None  # 审批ID（用于HITL）


@dataclass
class AuditLog:
    """审计日志记录"""
    timestamp: float
    tool_name: str
    risk_level: str
    action: str           # "execute" / "block" / "approval_requested" / "approved" / "rejected"
    tool_input: str
    result: str = ""
    duration: float = 0.0
    approved_by: str = ""


class ToolPermissionManager:
    """
    工具权限统一管理器

    职责：
    1. 维护工具风险等级注册表
    2. 执行工具前的权限检查
    3. DANGEROUS级工具的Human-in-the-loop审批
    4. 审计日志记录
    """

    def __init__(self):
        self._risk_registry: Dict[str, RiskLevel] = {}
        self._audit_logs: List[AuditLog] = []
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._approval_counter = 0

    def register_tool(self, tool_name: str, risk_level: RiskLevel) -> None:
        """
        注册工具风险等级

        Args:
            tool_name: 工具名称
            risk_level: 风险等级
        """
        self._risk_registry[tool_name] = risk_level
        logger.info(f"工具权限注册: {tool_name} → {risk_level.value} ({RISK_DESCRIPTIONS[risk_level]})")

    def get_risk_level(self, tool_name: str) -> RiskLevel:
        """
        获取工具风险等级

        Args:
            tool_name: 工具名称

        Returns:
            RiskLevel: 风险等级，未注册默认READ
        """
        return self._risk_registry.get(tool_name, RiskLevel.READ)

    def check_permission(self, tool_name: str, tool_input: Any) -> PermissionCheckResult:
        """
        执行工具前的权限检查

        Args:
            tool_name: 工具名称
            tool_input: 工具输入

        Returns:
            PermissionCheckResult: 权限检查结果
        """
        risk_level = self.get_risk_level(tool_name)
        requires_approval = (risk_level == RiskLevel.DANGEROUS)

        if requires_approval:
            self._approval_counter += 1
            approval_id = f"approval_{self._approval_counter}_{int(time.time())}"
            self._pending_approvals[approval_id] = {
                "tool_name": tool_name,
                "tool_input": str(tool_input)[:500],
                "risk_level": risk_level.value,
                "timestamp": time.time(),
                "status": "pending",
            }
            result = PermissionCheckResult(
                allowed=False,
                risk_level=risk_level,
                requires_approval=True,
                reason=f"工具 {tool_name} 风险等级为 {risk_level.value}，需要人工确认后才能执行",
                approval_id=approval_id,
            )
            logger.warning(f"权限检查: {tool_name} 需要人工审批 (approval_id={approval_id})")
        else:
            result = PermissionCheckResult(
                allowed=True,
                risk_level=risk_level,
                requires_approval=False,
                reason=f"工具 {tool_name} 风险等级为 {risk_level.value}，{EXECUTION_STRATEGIES[risk_level]}",
            )
            logger.debug(f"权限检查: {tool_name} 允许执行 ({risk_level.value})")

        return result

    def approve(self, approval_id: str, approved: bool, approved_by: str = "user") -> bool:
        """
        处理人工审批结果

        Args:
            approval_id: 审批ID
            approved: 是否批准
            approved_by: 审批人

        Returns:
            bool: 是否成功处理
        """
        if approval_id not in self._pending_approvals:
            logger.error(f"审批ID不存在: {approval_id}")
            return False

        approval = self._pending_approvals[approval_id]
        approval["status"] = "approved" if approved else "rejected"
        approval["approved_by"] = approved_by
        approval["resolved_at"] = time.time()

        action = "approved" if approved else "rejected"
        logger.info(f"人工审批: {approval['tool_name']} 被{action} (by {approved_by})")

        # 记录审计日志
        self._audit_logs.append(AuditLog(
            timestamp=time.time(),
            tool_name=approval["tool_name"],
            risk_level=approval["risk_level"],
            action=action,
            tool_input=approval["tool_input"],
            approved_by=approved_by,
        ))

        return True

    def is_approved(self, approval_id: str) -> Optional[bool]:
        """
        检查审批是否已处理

        Args:
            approval_id: 审批ID

        Returns:
            Optional[bool]: True=已批准, False=已拒绝, None=待处理
        """
        if approval_id not in self._pending_approvals:
            return None
        status = self._pending_approvals[approval_id]["status"]
        if status == "approved":
            return True
        elif status == "rejected":
            return False
        return None

    def log_execution(self, tool_name: str, tool_input: Any, result: str, duration: float) -> None:
        """
        记录工具执行审计日志

        Args:
            tool_name: 工具名称
            tool_input: 工具输入
            result: 执行结果
            duration: 执行耗时（秒）
        """
        risk_level = self.get_risk_level(tool_name).value
        self._audit_logs.append(AuditLog(
            timestamp=time.time(),
            tool_name=tool_name,
            risk_level=risk_level,
            action="execute",
            tool_input=str(tool_input)[:500],
            result=result[:500],
            duration=duration,
        ))

    def get_audit_logs(self, tool_name: Optional[str] = None, limit: int = 100) -> List[AuditLog]:
        """
        获取审计日志

        Args:
            tool_name: 按工具名称过滤，None表示全部
            limit: 返回条数上限

        Returns:
            List[AuditLog]: 审计日志列表
        """
        logs = self._audit_logs
        if tool_name:
            logs = [log for log in logs if log.tool_name == tool_name]
        return logs[-limit:]

    def get_permission_summary(self) -> Dict[str, Any]:
        """
        获取权限系统概览

        Returns:
            Dict: 包含注册工具数、审计日志数、待审批数等
        """
        return {
            "registered_tools": len(self._risk_registry),
            "risk_distribution": {
                level.value: sum(1 for v in self._risk_registry.values() if v == level)
                for level in RiskLevel
            },
            "audit_logs_total": len(self._audit_logs),
            "pending_approvals": sum(1 for a in self._pending_approvals.values() if a["status"] == "pending"),
            "execution_strategies": {level.value: EXECUTION_STRATEGIES[level] for level in RiskLevel},
        }


# 全局单例
_permission_manager: Optional[ToolPermissionManager] = None


def get_permission_manager() -> ToolPermissionManager:
    """获取权限管理器全局单例"""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = ToolPermissionManager()
    return _permission_manager


def register_default_tools() -> None:
    """
    注册默认工具的风险等级

    对应文档中的权限设计：
      READ      - Search, Calculator, SQL SELECT, RAG, Memory
      SANDBOX   - PythonExecutor
      DANGEROUS - SQL DELETE/UPDATE, File Delete, System Commands
    """
    pm = get_permission_manager()

    # READ级工具（只读，无副作用）
    read_tools = [
        "Search", "DuckDuckGoSearch", "SerpAPISearch",
        "Calculator", "MathCalculator",
        "SQLQuery", "SQLReadQuery",
        "DocQA", "RAGQuery", "DocumentQA",
        "MemoryRead", "MemorySearch", "MemoryRecall",
        "Weather",
    ]
    for tool in read_tools:
        pm.register_tool(tool, RiskLevel.READ)

    # SANDBOX级工具（受控环境执行）
    sandbox_tools = [
        "PythonExecutor", "PythonCodeInterpreter",
    ]
    for tool in sandbox_tools:
        pm.register_tool(tool, RiskLevel.SANDBOX)

    # DANGEROUS级工具（高风险，需人工确认）
    dangerous_tools = [
        "SQLWrite", "SQLDelete", "SQLUpdate", "SQLDrop",
        "FileDelete", "FileWrite", "FileModify",
        "SystemCommand", "ShellExec",
    ]
    for tool in dangerous_tools:
        pm.register_tool(tool, RiskLevel.DANGEROUS)

    logger.info("默认工具权限注册完成")
    summary = pm.get_permission_summary()
    logger.info(f"权限概览: {summary['risk_distribution']}")


# 模块自测
if __name__ == "__main__":
    print("=" * 60)
    print("工具权限管理系统自测")
    print("=" * 60)

    # 初始化
    register_default_tools()
    pm = get_permission_manager()

    # 测试READ级工具
    print("\n【测试READ级工具】")
    result = pm.check_permission("Search", "Python教程")
    print(f"  Search: allowed={result.allowed}, risk={result.risk_level.value}, approval={result.requires_approval}")

    # 测试SANDBOX级工具
    print("\n【测试SANDBOX级工具】")
    result = pm.check_permission("PythonExecutor", "print('hello')")
    print(f"  PythonExecutor: allowed={result.allowed}, risk={result.risk_level.value}, approval={result.requires_approval}")

    # 测试DANGEROUS级工具
    print("\n【测试DANGEROUS级工具】")
    result = pm.check_permission("SQLDelete", "DELETE FROM users WHERE id=1")
    print(f"  SQLDelete: allowed={result.allowed}, risk={result.risk_level.value}, approval={result.requires_approval}")
    print(f"  原因: {result.reason}")
    print(f"  审批ID: {result.approval_id}")

    # 测试人工审批
    print("\n【测试人工审批】")
    if result.approval_id:
        print(f"  审批前状态: {pm.is_approved(result.approval_id)}")
        pm.approve(result.approval_id, approved=True, approved_by="test_user")
        print(f"  审批后状态: {pm.is_approved(result.approval_id)}")

    # 测试审计日志
    print("\n【测试审计日志】")
    pm.log_execution("Search", "Python教程", "找到10条结果", 0.23)
    logs = pm.get_audit_logs(limit=5)
    print(f"  审计日志数: {len(logs)}")
    for log in logs:
        print(f"    [{log.tool_name}] {log.action} - {log.risk_level}")

    # 权限概览
    print("\n【权限系统概览】")
    summary = pm.get_permission_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 60)
    print("自测完成")
    print("=" * 60)
