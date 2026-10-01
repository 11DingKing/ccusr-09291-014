from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text, Float, Enum as SAEnum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, date
from database import Base
import enum


class VolunteerStatus(str, enum.Enum):
    PENDING_REVIEW = "报名待审"
    IN_TRAINING = "培训中"
    PENDING_ASSESSMENT = "待考核"
    CERTIFIED = "已持证"
    DISABLED = "已停用"


class AssessmentResult(str, enum.Enum):
    PENDING = "待考核"
    PASSED = "通过"
    FAILED = "未通过"


class TrainingBatchStatus(str, enum.Enum):
    DRAFT = "草稿"
    ENROLLING = "报名中"
    IN_PROGRESS = "进行中"
    COMPLETED = "已完成"
    CANCELLED = "已取消"


class EnrollmentStatus(str, enum.Enum):
    ENROLLED = "已入班"
    DROPPED = "已退班"
    COMPLETED = "已完成培训"


class WaitlistStatus(str, enum.Enum):
    WAITING = "候补中"
    PROMOTED = "已递补"
    DECLINED = "已放弃"
    CANCELLED = "已取消"


class WaitlistPriorityTier(int, enum.Enum):
    # 数字越小越优先；新增梯队只需在此调整，递补顺序自动生效
    SPECIAL_CARE = 1
    RETURNING = 2
    NORMAL = 3

    @property
    def label(self) -> str:
        return {
            WaitlistPriorityTier.SPECIAL_CARE: "优待对象",
            WaitlistPriorityTier.RETURNING: "老学员/已完成讲解服务",
            WaitlistPriorityTier.NORMAL: "普通登记",
        }[self]


class NotificationResult(str, enum.Enum):
    PENDING = "待通知"
    DELIVERED = "已送达"
    FAILED = "未送达"


class PromotionTrigger(str, enum.Enum):
    DROP = "学员退班"
    BATCH_DROP = "多人退班"
    WAITLIST_DECLINE = "候补放弃"
    CAPACITY_EXPAND = "临时扩容"
    MANUAL = "手动递补"


class TimeSlotStatus(str, enum.Enum):
    AVAILABLE = "可认领"
    CLAIMED = "已认领"
    COMPLETED = "已完成"
    CANCELLED = "已取消"


class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    contact_person = Column(String(50))
    contact_phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)

    volunteers = relationship("Volunteer", back_populates="school")


class StarLevel(Base):
    __tablename__ = "star_levels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(20), nullable=False, unique=True)
    min_hours = Column(Float, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    volunteers = relationship("Volunteer", back_populates="star_level")


class PointsType(str, enum.Enum):
    EARN = "获得"
    SPEND = "消耗"


class PointsSource(str, enum.Enum):
    SERVICE_COMPLETION = "完成讲解"
    TEACHER_RATING = "老师好评"
    EXCHANGE_BADGE = "兑换徽章"
    EXCHANGE_PRIORITY_SLOT = "兑换优先时段"
    OTHER = "其他"


class BenefitType(str, enum.Enum):
    BADGE = "纪念徽章"
    PRIORITY_SLOT = "优先认领时段"
    OTHER = "其他权益"


class ExchangeStatus(str, enum.Enum):
    PENDING = "待处理"
    COMPLETED = "已完成"
    CANCELLED = "已取消"


class Volunteer(Base):
    __tablename__ = "volunteers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    gender = Column(String(10))
    birth_date = Column(Date)
    school_id = Column(Integer, ForeignKey("schools.id"))
    grade = Column(String(20))
    parent_name = Column(String(50))
    parent_phone = Column(String(20))
    preferred_topic = Column(String(100))
    status = Column(SAEnum(VolunteerStatus), default=VolunteerStatus.PENDING_REVIEW)
    star_level_id = Column(Integer, ForeignKey("star_levels.id"))
    total_service_hours = Column(Float, default=0.0)
    points_balance = Column(Integer, default=0)
    registration_date = Column(Date, default=date.today)
    certification_date = Column(Date)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    school = relationship("School", back_populates="volunteers")
    star_level = relationship("StarLevel", back_populates="volunteers")
    trainings = relationship("TrainingAttendance", back_populates="volunteer")
    assessments = relationship("Assessment", back_populates="volunteer")
    time_slots = relationship("TimeSlot", back_populates="volunteer")
    service_records = relationship("ServiceRecord", back_populates="volunteer")
    enrollments = relationship("Enrollment", back_populates="volunteer")
    certifications = relationship("VolunteerCertification", back_populates="volunteer")
    points_records = relationship("PointsRecord", back_populates="volunteer")
    benefit_exchanges = relationship("BenefitExchange", back_populates="volunteer")
    star_certificates = relationship("StarCertificate", back_populates="volunteer")
    waitlist_entries = relationship("WaitlistEntry", back_populates="volunteer")


class AssessmentTopic(Base):
    __tablename__ = "assessment_topics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    pass_score = Column(Float, default=60.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    criteria = relationship("AssessmentCriterion", back_populates="topic")
    questions = relationship("AssessmentQuestion", back_populates="topic")
    assessments = relationship("Assessment", back_populates="topic_obj")
    certifications = relationship("VolunteerCertification", back_populates="topic")


class TrainingBatch(Base):
    __tablename__ = "training_batches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    topic_id = Column(Integer, ForeignKey("assessment_topics.id"))
    description = Column(Text)
    min_attendance_rate = Column(Float, default=80.0)
    capacity = Column(Integer, default=30)
    status = Column(SAEnum(TrainingBatchStatus), default=TrainingBatchStatus.DRAFT)
    start_date = Column(Date)
    end_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    topic = relationship("AssessmentTopic")
    sessions = relationship("TrainingSession", back_populates="batch", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="batch", cascade="all, delete-orphan")
    assessments = relationship("Assessment", back_populates="training_batch")
    waitlist_entries = relationship("WaitlistEntry", back_populates="batch", cascade="all, delete-orphan")
    promotions = relationship("WaitlistPromotion", back_populates="batch", cascade="all, delete-orphan")


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("training_batches.id"), nullable=False)
    session_no = Column(Integer, nullable=False)
    title = Column(String(100), nullable=False)
    session_date = Column(Date, nullable=False)
    start_time = Column(String(10))
    end_time = Column(String(10))
    location = Column(String(100))
    trainer = Column(String(50))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    batch = relationship("TrainingBatch", back_populates="sessions")
    attendances = relationship("SessionAttendance", back_populates="session", cascade="all, delete-orphan")


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("training_batches.id"), nullable=False)
    status = Column(SAEnum(EnrollmentStatus), default=EnrollmentStatus.ENROLLED)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    notes = Column(Text)

    volunteer = relationship("Volunteer", back_populates="enrollments")
    batch = relationship("TrainingBatch", back_populates="enrollments")
    attendances = relationship("SessionAttendance", back_populates="enrollment", cascade="all, delete-orphan")


class WaitlistEntry(Base):
    """培训期次候补登记。

    顺序由 (priority_tier, seq_no) 唯一确定：先按优先级梯队，梯队相同按登记
    先后（seq_no 为期次内单调递增序号，不受放弃/取消记录影响，保证重新登记
    必然排到同梯队队尾）。promotion_seq 记录该人在某轮递补中的入选顺位。
    """
    __tablename__ = "waitlist_entries"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("training_batches.id"), nullable=False)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"), nullable=False)
    # 优先级梯队（数字越小越优先）与登记时固化的依据说明
    priority_tier = Column(Integer, nullable=False, default=lambda: WaitlistPriorityTier.NORMAL.value)
    priority_label = Column(String(50), nullable=False)
    priority_reason = Column(Text, nullable=False)
    # 期次内单调递增的登记序号；同优先级先到先得
    seq_no = Column(Integer, nullable=False)
    status = Column(SAEnum(WaitlistStatus), nullable=False, default=WaitlistStatus.WAITING)
    # 通知送达情况
    notify_status = Column(SAEnum(NotificationResult), nullable=False, default=NotificationResult.PENDING)
    notified_at = Column(DateTime)
    notify_detail = Column(Text)
    # 递补/放弃/取消的审计信息
    promotion_id = Column(Integer, ForeignKey("waitlist_promotions.id"))
    promotion_seq = Column(Integer)
    promoted_at = Column(DateTime)
    declined_at = Column(DateTime)
    decline_reason = Column(Text)
    cancelled_at = Column(DateTime)
    cancel_reason = Column(Text)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    batch = relationship("TrainingBatch", back_populates="waitlist_entries")
    volunteer = relationship("Volunteer", back_populates="waitlist_entries")
    promotion = relationship("WaitlistPromotion", back_populates="entries", foreign_keys=[promotion_id])


class WaitlistPromotion(Base):
    """一轮名额释放后的一次性递补记录（多人同时退班也只产生一轮）。"""
    __tablename__ = "waitlist_promotions"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("training_batches.id"), nullable=False)
    trigger = Column(SAEnum(PromotionTrigger), nullable=False)
    # 本轮触发前在班人数、释放/新增的名额数、本轮可用空位
    seats_before = Column(Integer, nullable=False)
    seats_released = Column(Integer, nullable=False, default=0)
    seats_available = Column(Integer, nullable=False)
    promoted_count = Column(Integer, nullable=False, default=0)
    detail = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    batch = relationship("TrainingBatch", back_populates="promotions")
    entries = relationship("WaitlistEntry", back_populates="promotion", foreign_keys="WaitlistEntry.promotion_id")


class SessionAttendance(Base):
    __tablename__ = "session_attendances"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(Integer, ForeignKey("enrollments.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("training_sessions.id"), nullable=False)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"), nullable=False)
    attended = Column(Boolean, default=False)
    late = Column(Boolean, default=False)
    leave_early = Column(Boolean, default=False)
    checked_at = Column(DateTime)
    remarks = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    enrollment = relationship("Enrollment", back_populates="attendances")
    session = relationship("TrainingSession", back_populates="attendances")
    volunteer = relationship("Volunteer")


class AssessmentCriterion(Base):
    __tablename__ = "assessment_criteria"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("assessment_topics.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    max_score = Column(Float, default=20.0)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("AssessmentTopic", back_populates="criteria")
    scores = relationship("AssessmentScore", back_populates="criterion", cascade="all, delete-orphan")


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("assessment_topics.id"), nullable=False)
    question = Column(Text, nullable=False)
    reference_answer = Column(Text)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("AssessmentTopic", back_populates="questions")


class AssessmentScore(Base):
    __tablename__ = "assessment_scores"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    criterion_id = Column(Integer, ForeignKey("assessment_criteria.id"), nullable=False)
    score = Column(Float, default=0.0)
    comments = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="scores")
    criterion = relationship("AssessmentCriterion", back_populates="scores")


class VolunteerCertification(Base):
    __tablename__ = "volunteer_certifications"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"), nullable=False)
    topic_id = Column(Integer, ForeignKey("assessment_topics.id"), nullable=False)
    assessment_id = Column(Integer, ForeignKey("assessments.id"))
    certificate_no = Column(String(50), unique=True)
    issued_date = Column(Date, default=date.today)
    expiry_date = Column(Date)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    volunteer = relationship("Volunteer", back_populates="certifications")
    topic = relationship("AssessmentTopic", back_populates="certifications")
    assessment = relationship("Assessment")


class Training(Base):
    __tablename__ = "trainings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    training_date = Column(Date, nullable=False)
    start_time = Column(String(10))
    end_time = Column(String(10))
    location = Column(String(100))
    trainer = Column(String(50))
    content = Column(Text)
    max_participants = Column(Integer, default=30)
    created_at = Column(DateTime, default=datetime.utcnow)

    attendances = relationship("TrainingAttendance", back_populates="training")


class TrainingAttendance(Base):
    __tablename__ = "training_attendances"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"))
    training_id = Column(Integer, ForeignKey("trainings.id"))
    attended = Column(Integer, default=0)
    remarks = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    volunteer = relationship("Volunteer", back_populates="trainings")
    training = relationship("Training", back_populates="attendances")


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"), nullable=False)
    topic_id = Column(Integer, ForeignKey("assessment_topics.id"))
    training_batch_id = Column(Integer, ForeignKey("training_batches.id"))
    parent_assessment_id = Column(Integer, ForeignKey("assessments.id"))
    assessment_date = Column(Date, nullable=False)
    topic = Column(String(100))
    score = Column(Float)
    result = Column(SAEnum(AssessmentResult), default=AssessmentResult.PENDING)
    is_retake = Column(Boolean, default=False)
    attempt_no = Column(Integer, default=1)
    examiner = Column(String(50))
    comments = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    volunteer = relationship("Volunteer", back_populates="assessments")
    topic_obj = relationship("AssessmentTopic", back_populates="assessments")
    training_batch = relationship("TrainingBatch", back_populates="assessments")
    parent_assessment = relationship("Assessment", remote_side=[id])
    scores = relationship("AssessmentScore", back_populates="assessment", cascade="all, delete-orphan")
    certification = relationship("VolunteerCertification", back_populates="assessment", uselist=False)


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id = Column(Integer, primary_key=True, index=True)
    slot_date = Column(Date, nullable=False)
    start_time = Column(String(10), nullable=False)
    end_time = Column(String(10), nullable=False)
    topic = Column(String(100))
    location = Column(String(100))
    status = Column(SAEnum(TimeSlotStatus), default=TimeSlotStatus.AVAILABLE)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    volunteer = relationship("Volunteer", back_populates="time_slots")
    service_record = relationship("ServiceRecord", back_populates="time_slot", uselist=False)


class ServiceRecord(Base):
    __tablename__ = "service_records"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"))
    time_slot_id = Column(Integer, ForeignKey("time_slots.id"))
    service_date = Column(Date, nullable=False)
    service_hours = Column(Float, nullable=False)
    audience_count = Column(Integer, default=0)
    teacher_name = Column(String(50))
    teacher_rating = Column(Integer)
    teacher_comments = Column(Text)
    points_awarded = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    volunteer = relationship("Volunteer", back_populates="service_records")
    time_slot = relationship("TimeSlot", back_populates="service_record")


class PointsRecord(Base):
    __tablename__ = "points_records"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"), nullable=False)
    points_type = Column(SAEnum(PointsType), nullable=False)
    points_amount = Column(Integer, nullable=False)
    source = Column(SAEnum(PointsSource), nullable=False)
    service_record_id = Column(Integer, ForeignKey("service_records.id"))
    exchange_id = Column(Integer, ForeignKey("benefit_exchanges.id"))
    description = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    volunteer = relationship("Volunteer", back_populates="points_records")
    service_record = relationship("ServiceRecord")
    exchange = relationship("BenefitExchange", back_populates="points_record")


class Benefit(Base):
    __tablename__ = "benefits"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    benefit_type = Column(SAEnum(BenefitType), nullable=False)
    description = Column(Text)
    points_cost = Column(Integer, nullable=False)
    stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    image_url = Column(String(500))
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    exchanges = relationship("BenefitExchange", back_populates="benefit")


class BenefitExchange(Base):
    __tablename__ = "benefit_exchanges"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"), nullable=False)
    benefit_id = Column(Integer, ForeignKey("benefits.id"), nullable=False)
    points_spent = Column(Integer, nullable=False)
    status = Column(SAEnum(ExchangeStatus), default=ExchangeStatus.PENDING)
    quantity = Column(Integer, default=1)
    delivery_info = Column(Text)
    fulfilled_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    volunteer = relationship("Volunteer", back_populates="benefit_exchanges")
    benefit = relationship("Benefit", back_populates="exchanges")
    points_record = relationship("PointsRecord", back_populates="exchange", uselist=False)


class StarCertificate(Base):
    __tablename__ = "star_certificates"

    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"), nullable=False)
    star_level_id = Column(Integer, ForeignKey("star_levels.id"), nullable=False)
    certificate_no = Column(String(50), unique=True, nullable=False)
    issued_date = Column(Date, default=date.today)
    total_hours = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    volunteer = relationship("Volunteer", back_populates="star_certificates")
    star_level = relationship("StarLevel")
