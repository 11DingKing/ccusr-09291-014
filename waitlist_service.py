"""候补队列领域服务。

顺序规则（任何场景都不得打乱）：
    排序键 = (priority_tier 升序, seq_no 升序)
即先比优先级梯队，梯队相同再比期次内单调递增的登记序号。名额释放时，在同一个
事务/同一轮次里按该顺序一次性填满所有空位，多人同时退班、临时扩容都只产生一轮
递补（见 WaitlistPromotion）。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

import models
import schemas

ELIGIBLE_VOLUNTEER_STATUSES = (
    models.VolunteerStatus.IN_TRAINING,
    models.VolunteerStatus.PENDING_ASSESSMENT,
)


# ==================== 基础查询 ====================

def get_batch(db: Session, batch_id: int) -> Optional[models.TrainingBatch]:
    return db.query(models.TrainingBatch).filter(
        models.TrainingBatch.id == batch_id
    ).first()


def enrolled_count(db: Session, batch_id: int) -> int:
    return db.query(func.count(models.Enrollment.id)).filter(
        models.Enrollment.batch_id == batch_id,
        models.Enrollment.status == models.EnrollmentStatus.ENROLLED,
    ).scalar() or 0


def waiting_query(db: Session, batch_id: int):
    return db.query(models.WaitlistEntry).filter(
        models.WaitlistEntry.batch_id == batch_id,
        models.WaitlistEntry.status == models.WaitlistStatus.WAITING,
    )


def waiting_entries(db: Session, batch_id: int):
    """候补队列的唯一排序入口：梯队优先，同梯队按登记序号。"""
    return waiting_query(db, batch_id).order_by(
        models.WaitlistEntry.priority_tier.asc(),
        models.WaitlistEntry.seq_no.asc(),
    ).all()


def count_ahead(db: Session, entry: models.WaitlistEntry) -> int:
    """排在该候补者前面的人数：梯队更高，或同梯队登记更早。"""
    return waiting_query(db, entry.batch_id).filter(
        or_(
            models.WaitlistEntry.priority_tier < entry.priority_tier,
            and_(
                models.WaitlistEntry.priority_tier == entry.priority_tier,
                models.WaitlistEntry.seq_no < entry.seq_no,
            ),
        )
    ).count()


def next_seq_no(db: Session, batch_id: int) -> int:
    # 含历史记录取最大值：放弃/取消后重新登记必然排到同梯队队尾
    max_seq = db.query(func.max(models.WaitlistEntry.seq_no)).filter(
        models.WaitlistEntry.batch_id == batch_id
    ).scalar()
    return (max_seq or 0) + 1


def validate_tier(tier: int) -> models.WaitlistPriorityTier:
    try:
        return models.WaitlistPriorityTier(tier)
    except (ValueError, TypeError):
        raise ValueError("priority_tier 必须为 1(优待对象) / 2(老学员) / 3(普通登记)")


# ==================== 登记 ====================

def register(
    db: Session,
    batch: models.TrainingBatch,
    volunteer_id: int,
    tier: models.WaitlistPriorityTier,
    reason: Optional[str],
) -> models.WaitlistEntry:
    volunteer = db.query(models.Volunteer).filter(
        models.Volunteer.id == volunteer_id
    ).first()
    if not volunteer:
        raise LookupError("志愿者不存在")
    if volunteer.status not in ELIGIBLE_VOLUNTEER_STATUSES:
        raise PermissionError(f"志愿者状态({volunteer.status.value})不可报名入班")

    # 重复报名防护 1：已在班（含历史在班）不允许候补
    active_enrollment = db.query(models.Enrollment).filter(
        models.Enrollment.batch_id == batch.id,
        models.Enrollment.volunteer_id == volunteer_id,
        models.Enrollment.status == models.EnrollmentStatus.ENROLLED,
    ).first()
    if active_enrollment:
        raise PermissionError("已在该期次在班，无需候补")

    # 重复报名防护 2：已有候补中记录（放弃/取消/已递补的历史记录不阻止重新登记，
    # 但新记录会拿到更大的 seq_no，自动排到队尾）
    active_wait = waiting_query(db, batch.id).filter(
        models.WaitlistEntry.volunteer_id == volunteer_id
    ).first()
    if active_wait:
        raise PermissionError("已在该期次候补队列中，请勿重复登记")

    priority_reason = reason.strip() if reason and reason.strip() else tier.label
    entry = models.WaitlistEntry(
        batch_id=batch.id,
        volunteer_id=volunteer_id,
        priority_tier=tier.value,
        priority_label=tier.label,
        priority_reason=priority_reason,
        seq_no=next_seq_no(db, batch.id),
        status=models.WaitlistStatus.WAITING,
        notify_status=models.NotificationResult.PENDING,
    )
    db.add(entry)

    # 若登记时仍有空位（例如期次刚开放），直接登记入班而不占候补序号的语义
    # 由调用方决定；候补只在名额已满时发挥作用，这里不自动递补。
    db.flush()
    return entry


# ==================== 放弃 / 取消 ====================

def decline(db: Session, entry: models.WaitlistEntry, reason: Optional[str]):
    """放弃候补。返回值 > 0 表示放弃的是已递补名额，调用方需随即触发一轮递补。"""
    if entry.status == models.WaitlistStatus.WAITING:
        entry.status = models.WaitlistStatus.DECLINED
        entry.declined_at = datetime.utcnow()
        entry.decline_reason = reason
        return 0
    if entry.status == models.WaitlistStatus.PROMOTED:
        # 已递补者放弃：连同其在班名额一并退出，名额留给后续候补
        enrollment = db.query(models.Enrollment).filter(
            models.Enrollment.batch_id == entry.batch_id,
            models.Enrollment.volunteer_id == entry.volunteer_id,
            models.Enrollment.status == models.EnrollmentStatus.ENROLLED,
        ).first()
        entry.status = models.WaitlistStatus.DECLINED
        entry.declined_at = datetime.utcnow()
        entry.decline_reason = reason or "入选后放弃名额"
        if enrollment:
            enrollment.status = models.EnrollmentStatus.DROPPED
            return 1
        return 0
    raise PermissionError(f"当前状态({entry.status.value})不可放弃")


def cancel(db: Session, entry: models.WaitlistEntry, reason: Optional[str]):
    if entry.status != models.WaitlistStatus.WAITING:
        raise PermissionError(f"当前状态({entry.status.value})不可取消")
    entry.status = models.WaitlistStatus.CANCELLED
    entry.cancelled_at = datetime.utcnow()
    entry.cancel_reason = reason


# ==================== 通知送达 ====================

def record_notification(db: Session, entry: models.WaitlistEntry, delivered: bool,
                        detail: Optional[str]):
    if entry.status != models.WaitlistStatus.PROMOTED:
        raise PermissionError("仅已递补人员需要登记通知结果")
    entry.notify_status = (
        models.NotificationResult.DELIVERED if delivered
        else models.NotificationResult.FAILED
    )
    entry.notified_at = datetime.utcnow()
    entry.notify_detail = detail


# ==================== 一次性递补 ====================

def run_promotion(
    db: Session,
    batch: models.TrainingBatch,
    trigger: models.PromotionTrigger,
    seats_released: int = 0,
    seats_before: Optional[int] = None,
) -> schemas.WaitlistPromotionResult:
    """按 (梯队, 登记序号) 一次性填满当前全部空位。

    多人同时退班时，调用方应先在同一事务内完成全部退班，再调用一次本函数，
    seats_released 传入退班总人数 —— 只产生一轮递补，顺序不会被逐个退班打乱。
    """
    if seats_before is None:
        seats_before = enrolled_count(db, batch.id)
    seats_available = max(batch.capacity - seats_before, 0)

    candidates = waiting_entries(db, batch.id)

    record = models.WaitlistPromotion(
        batch_id=batch.id,
        trigger=trigger,
        seats_before=seats_before,
        seats_released=seats_released,
        seats_available=seats_available,
        promoted_count=0,
    )
    db.add(record)
    db.flush()

    promoted_items = []
    seq = 0
    taken = 0
    for entry in candidates:
        if taken >= seats_available:
            break
        volunteer = db.query(models.Volunteer).filter(
            models.Volunteer.id == entry.volunteer_id
        ).first()

        # 资格失效者不参与递补，记为取消并说明原因，后续人员依次顶上，顺序不乱
        invalid_reason = None
        if not volunteer or volunteer.status not in ELIGIBLE_VOLUNTEER_STATUSES:
            invalid_reason = "递补时志愿者状态已不满足入班条件，自动跳过"
        else:
            dup = db.query(models.Enrollment).filter(
                models.Enrollment.batch_id == batch.id,
                models.Enrollment.volunteer_id == entry.volunteer_id,
                models.Enrollment.status == models.EnrollmentStatus.ENROLLED,
            ).first()
            if dup:
                invalid_reason = "该志愿者已通过其他途径入班，自动跳过"
        if invalid_reason:
            entry.status = models.WaitlistStatus.CANCELLED
            entry.cancelled_at = datetime.utcnow()
            entry.cancel_reason = invalid_reason
            continue

        seq += 1
        enrollment = models.Enrollment(
            volunteer_id=entry.volunteer_id,
            batch_id=batch.id,
            status=models.EnrollmentStatus.ENROLLED,
        )
        db.add(enrollment)
        entry.status = models.WaitlistStatus.PROMOTED
        entry.promotion_id = record.id
        entry.promotion_seq = seq
        entry.promoted_at = datetime.utcnow()
        entry.notify_status = models.NotificationResult.PENDING
        promoted_items.append((entry, volunteer))
        taken += 1

    record.promoted_count = seq
    names = "、".join(v.name for _, v in promoted_items) or "无"
    record.detail = (
        f"触发：{trigger.value}；递补前在班{seats_before}人，容量{batch.capacity}，"
        f"可用空位{seats_available}个；按优先级梯队+登记序号一次性递补{seq}人：{names}"
    )
    db.flush()
    db.commit()
    db.refresh(record)

    still = build_queue(db, batch.id)
    return schemas.WaitlistPromotionResult(
        batch_id=batch.id,
        trigger=record.trigger,
        seats_before=seats_before,
        seats_released=seats_released,
        seats_available=seats_available,
        promoted_count=seq,
        promoted=[
            schemas.WaitlistPromotionItem(
                waitlist_id=e.id,
                volunteer_id=e.volunteer_id,
                volunteer_name=v.name,
                promotion_seq=e.promotion_seq,
                priority_tier=e.priority_tier,
                priority_label=e.priority_label,
                notify_status=e.notify_status,
            )
            for e, v in promoted_items
        ],
        still_waiting=still,
        message=f"本轮一次性递补 {seq} 人，仍有 {len(still)} 人候补；"
                f"资格失效或已入班的候补者已自动跳过并保留记录",
    )


# ==================== 对外说明 ====================

def build_queue_item(db: Session, entry: models.WaitlistEntry,
                     position: Optional[int] = None) -> schemas.WaitlistQueueItem:
    data = schemas.WaitlistEntry.model_validate(entry)
    item = schemas.WaitlistQueueItem(**data.model_dump())
    item.queue_position = position
    item.explanation = explain(db, entry, position)
    return item


def build_queue(db: Session, batch_id: int) -> list:
    entries = waiting_entries(db, batch_id)
    return [build_queue_item(db, e, position=i + 1) for i, e in enumerate(entries)]


def explain(db: Session, entry: models.WaitlistEntry,
            position: Optional[int] = None) -> str:
    """接口直接返回的入选/等待理由，工作人员可转述给家长。"""
    basis = f"优先级依据：{entry.priority_label}（{entry.priority_reason}），登记序号第{entry.seq_no}号"

    if entry.status == models.WaitlistStatus.WAITING:
        if position is None:
            position = count_ahead(db, entry) + 1
        batch = entry.batch or get_batch(db, entry.batch_id)
        current = enrolled_count(db, entry.batch_id)
        capacity = batch.capacity if batch else "?"
        ahead = count_ahead(db, entry)
        return (
            f"仍在等待：{basis}；当前队内第{position}位（同梯队按登记序号先后排序），"
            f"前面还有{ahead}人；在班{current}/{capacity}人，"
            f"需按顺序等待名额释放，工作人员不可跨人补位。"
        )

    if entry.status == models.WaitlistStatus.PROMOTED:
        notify = {
            models.NotificationResult.PENDING: "待通知",
            models.NotificationResult.DELIVERED: f"通知已送达（{entry.notify_detail or '已确认'}）",
            models.NotificationResult.FAILED: f"通知未送达（{entry.notify_detail or '待重拨'}）",
        }[entry.notify_status]
        return (
            f"已入选：{basis}；在第{entry.promotion_id}轮递补中第{entry.promotion_seq}位入选"
            f"（递补时间{entry.promoted_at:%Y-%m-%d %H:%M}），{notify}。"
        )

    if entry.status == models.WaitlistStatus.DECLINED:
        return f"已放弃候补：{basis}；放弃时间{entry.declined_at:%Y-%m-%d %H:%M}。{entry.decline_reason or ''}"
    if entry.status == models.WaitlistStatus.CANCELLED:
        return f"候补已取消：{basis}；{entry.cancel_reason or '工作人员取消'}"
    return basis
