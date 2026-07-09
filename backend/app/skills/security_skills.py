"""Hardcoded security operation procedures (Skills) for high-risk incidents.

Skill 1: breach_containment_plan — Data breach containment protocol
Skill 2: secops_handoff_summary — Security handoff summary generation
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ContainmentResult:
    """Result of executing the breach containment plan."""
    skill_name: str = "breach_containment_plan"
    triggered: bool = True
    instructions: list[str] = field(default_factory=lambda: [
        "🔴 安全模式已激活 — 请立即执行以下操作：",
        "",
        "1. **物理隔离**：立即断开受影响设备的所有网络连接（Wi-Fi / 网线 / 蓝牙）",
        "2. **账号锁定**：在 AD 控制台立即禁用涉及的用户账号",
        "3. **凭证重置**：强制重置所有与该设备相关的账号密码",
        "4. **保留证据**：不要删除任何文件或日志，保留原始磁盘镜像",
        "5. **上报安全团队**：通过 SecOps Dashboard 或内线电话立即通知安全运维团队",
        "",
        "⚠️ 在安全团队接管前，请勿进行任何其他操作。",
    ])
    ui_mode: str = "security_red"  # Triggers red-themed UI on the frontend


def execute_breach_containment(state: dict) -> ContainmentResult:
    """Execute Skill 1: Data breach containment plan.

    Triggered when SecurityGuardian detects a RISK-level event.
    Returns containment instructions and signals the frontend to switch
    to red security mode.
    """
    return ContainmentResult()


@dataclass
class HandoffSummary:
    """Security operations handoff summary."""
    skill_name: str = "secops_handoff_summary"
    incident_time: str = ""
    involved_ip: str = ""
    involved_user: str = ""
    data_classification: str = ""  # e.g., PII, financial, internal
    affected_systems: list[str] = field(default_factory=list)
    summary: str = ""
    recommended_actions: list[str] = field(default_factory=list)


def generate_handoff_summary(
    state: dict,
    incident_time: str = "",
    involved_ip: str = "",
    involved_user: str = "",
    data_classification: str = "",
    affected_systems: list[str] | None = None,
) -> HandoffSummary:
    """Execute Skill 2: Generate a formatted security handoff summary.

    Collects key entities (time, IP, classification level, affected systems)
    and produces a structured summary for the SecOps Dashboard.

    Args:
        state: Current agent state containing security context.
        incident_time: When the incident was detected.
        involved_ip: IP address(es) involved.
        involved_user: User account(s) involved.
        data_classification: Data sensitivity level.
        affected_systems: List of affected system names.

    Returns:
        A formatted HandoffSummary ready for WebSocket push to dashboard.
    """
    summary_parts = [
        f"⏰ 事件时间：{incident_time or datetime.now().isoformat()}",
        f"🌐 涉及 IP：{involved_ip or '待确认'}",
        f"👤 涉及用户：{involved_user or '待确认'}",
        f"📊 数据密级：{data_classification or '待评估'}",
        f"🖥️ 受影响系统：{', '.join(affected_systems) if affected_systems else '待确认'}",
    ]

    return HandoffSummary(
        incident_time=incident_time or datetime.now().isoformat(),
        involved_ip=involved_ip,
        involved_user=involved_user,
        data_classification=data_classification,
        affected_systems=affected_systems or [],
        summary="\n".join(summary_parts),
        recommended_actions=[
            "立即隔离受影响系统",
            "启动事件响应流程",
            "通知数据保护官 (DPO)",
            "收集并保全数字证据",
            "在 24 小时内提交初步事故报告",
        ],
    )
