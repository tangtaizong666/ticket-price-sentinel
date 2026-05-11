from dataclasses import dataclass

from app.history import get_session_state
from app.monitoring import count_enabled_monitor_tasks, get_latest_monitor_hit
from app.settings import Settings


@dataclass(slots=True)
class DashboardCard:
    title: str
    status: str
    detail: str
    action_label: str
    action_kind: str
    monitor_task_id: int | None = None
    monitor_hit_id: int | None = None


@dataclass(slots=True)
class HomeDashboard:
    guide_title: str
    guide_steps: list[str]
    login_card: DashboardCard
    monitor_card: DashboardCard
    latest_hit_card: DashboardCard


def load_home_dashboard(settings: Settings) -> HomeDashboard:
    session_state = get_session_state(settings)
    enabled_count = count_enabled_monitor_tasks(settings)
    latest_hit = get_latest_monitor_hit(settings)

    if session_state is not None and session_state.session_status == "login_started":
        login_card = DashboardCard(
            title="登录状态",
            status="登录进行中",
            detail="已打开登录窗口，请在携程完成登录",
            action_label="继续登录",
            action_kind="relogin",
        )
    else:
        login_card = DashboardCard(
            title="登录状态",
            status="未登录",
            detail="首次使用请先登录携程",
            action_label="去登录",
            action_kind="relogin",
        )

    if enabled_count == 0:
        monitor_card = DashboardCard(
            title="监控状态",
            status="还没有监控任务",
            detail="保存一个目标价，程序会在后台帮你定时检查",
            action_label="创建第一个监控",
            action_kind="create-monitor",
        )
    else:
        monitor_card = DashboardCard(
            title="监控状态",
            status=f"{enabled_count} 个任务正在运行",
            detail="后台监控已启用",
            action_label="创建监控任务",
            action_kind="create-monitor",
        )

    if latest_hit is None:
        latest_hit_card = DashboardCard(
            title="最近命中",
            status="还没有命中记录",
            detail="当价格达到你的目标价时，最新命中结果会显示在这里",
            action_label="创建监控任务",
            action_kind="create-monitor",
        )
    else:
        task, hit = latest_hit
        latest_hit_card = DashboardCard(
            title="最近命中",
            status=f"{task.origin_city} → {task.destination_city}",
            detail=f"最低价 ¥{hit.lowest_price}",
            action_label="查看命中结果",
            action_kind="view-hit",
            monitor_task_id=task.id,
            monitor_hit_id=hit.id,
        )

    return HomeDashboard(
        guide_title="只要 3 步就能开始",
        guide_steps=[
            "先确认携程是否已登录",
            "做一次搜索看看现在的价格",
            "保存一个监控任务，后台自动帮你检查",
        ],
        login_card=login_card,
        monitor_card=monitor_card,
        latest_hit_card=latest_hit_card,
    )
