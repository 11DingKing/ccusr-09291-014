"""候补队列端到端验收测试。

覆盖：优先级依据保存、同优先级先到先得、单人/多人退班一次性递补、
候选人放弃、入选后放弃释放名额、临时扩容、重复报名防护、通知送达
记录，以及接口直接给出“为何入选/为何仍在等待”的说明。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 使用独立的临时数据库，避免与脚本式 test_api.py 删除/重建 redscarf.db 相互影响
import database
from sqlalchemy import create_engine
import main  # noqa: F401  确保全部模型已注册到 Base

_tmp_dir = tempfile.mkdtemp(prefix="waitlist_test_")
_test_engine = create_engine(
    f"sqlite:///{_tmp_dir}/waitlist.db",
    connect_args={"check_same_thread": False},
)
database.SessionLocal.configure(bind=_test_engine)
database.Base.metadata.create_all(bind=_test_engine)

from seed_data import seed_data

_seed_db = database.SessionLocal()
try:
    seed_data(_seed_db)
finally:
    _seed_db.close()

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def make_volunteer(name):
    r = client.get("/api/schools")
    school_id = r.json()[0]["id"]
    r = client.post("/api/volunteers/", json={
        "name": name, "school_id": school_id, "grade": "三年级",
        "parent_name": name + "家长", "parent_phone": "139000000" + name[-1],
    })
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    r = client.put(f"/api/volunteers/{vid}", json={"status": "培训中"})
    assert r.status_code == 200, r.text
    return vid


def make_batch(name, capacity):
    r = client.post("/api/trainings/batches", json={
        "name": name, "capacity": capacity,
        "start_date": "2026-07-01", "end_date": "2026-07-20",
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def register_wait(batch_id, vid, tier, reason):
    r = client.post(f"/api/trainings/batches/{batch_id}/waitlist", json={
        "batch_id": batch_id, "volunteer_id": vid,
        "priority_tier": tier, "priority_reason": reason,
    })
    assert r.status_code == 201, r.text
    return r.json()


def waitlist_ids(batch_id):
    r = client.get(f"/api/trainings/batches/{batch_id}/waitlist")
    assert r.status_code == 200, r.text
    return [(e["volunteer_id"], e) for e in r.json()]


def test_waitlist_full_flow():
    # A B C D E F G 七名孩子
    A, B, C, D, E, F, G = [make_volunteer(n) for n in
                           ("候补甲", "候补乙", "候补丙", "候补丁", "候补戊", "候补己", "候补庚")]
    batch_id = make_batch("2026暑期热门讲解班", 3)

    # 报满 3 人
    r = client.post("/api/trainings/enrollments/batch",
                    json={"batch_id": batch_id, "volunteer_ids": [A, B, C]})
    assert r.status_code == 200
    assert r.json()["enrolled_count"] == 3

    # 候补登记顺序刻意打乱：普通→优待→优待→老学员
    wd = register_wait(batch_id, D, 3, "普通登记，7月1日现场登记")
    we = register_wait(batch_id, E, 1, "烈属子女，持证明")
    wf = register_wait(batch_id, F, 1, "抗疫一线医护人员子女")
    wg = register_wait(batch_id, G, 2, "2025冬令营老学员")

    # 同优先级先到先得 + 梯队整体优先：E(优待,序号2) > F(优待,序号3) > G(老学员) > D(普通)
    queue = waitlist_ids(batch_id)
    assert [vid for vid, _ in queue] == [E, F, G, D]
    assert [e["queue_position"] for _, e in queue] == [1, 2, 3, 4]

    # 优先级依据被保存
    assert queue[0][1]["priority_label"] == "优待对象"
    assert queue[0][1]["priority_reason"] == "烈属子女，持证明"

    # 接口直接说明为何仍在等待（更早登记的普通孩子 D 排在优待之后也能解释清楚）
    d_explain = queue[3][1]["explanation"]
    assert "仍在等待" in d_explain and "前面还有3人" in d_explain and "第4位" in d_explain

    # 重复报名防护
    r = client.post(f"/api/trainings/batches/{batch_id}/waitlist", json={
        "batch_id": batch_id, "volunteer_id": D, "priority_tier": 3})
    assert r.status_code == 400
    r = client.post(f"/api/trainings/batches/{batch_id}/waitlist", json={
        "batch_id": batch_id, "volunteer_id": 999999, "priority_tier": 3})
    assert r.status_code == 404
    r = client.post(f"/api/trainings/batches/{batch_id}/waitlist", json={
        "batch_id": batch_id, "volunteer_id": A, "priority_tier": 3})
    assert r.status_code == 400  # 已在班
    r = client.post(f"/api/trainings/batches/{batch_id}/waitlist", json={
        "batch_id": batch_id, "volunteer_id": D, "priority_tier": 9})
    assert r.status_code == 400  # 非法梯队

    # 单人退班：E 第一位入选
    enr_A = [e for e in client.get(
        f"/api/trainings/batches/{batch_id}/enrollments").json()
        if e["volunteer_id"] == A][0]["id"]
    r = client.post(f"/api/trainings/enrollments/{enr_A}/drop")
    assert r.status_code == 200, r.text
    promo = r.json()["promotion"]
    assert promo["trigger"] == "学员退班"
    assert promo["seats_released"] == 1 and promo["promoted_count"] == 1
    assert promo["promoted"][0]["volunteer_id"] == E
    assert [e["volunteer_id"] for e in promo["still_waiting"]] == [F, G, D]

    # 通知送达记录
    r = client.post(f"/api/trainings/waitlist/{we['id']}/notify",
                    json={"delivered": True, "detail": "家长电话确认参加"})
    assert r.status_code == 200
    assert "已入选" in r.json()["explanation"] and "通知已送达" in r.json()["explanation"]

    # 多人同时退班：B、C 同时退出，只产生一轮递补，F、G 一次性入选且顺序正确
    r = client.post(f"/api/trainings/batches/{batch_id}/enrollments/batch-drop",
                    json={"volunteer_ids": [B, C]})
    assert r.status_code == 200, r.text
    promo2 = r.json()
    assert promo2["trigger"] == "多人退班"
    assert promo2["seats_released"] == 2
    assert [p["volunteer_id"] for p in promo2["promoted"]] == [F, G]
    assert [p["promotion_seq"] for p in promo2["promoted"]] == [1, 2]
    assert [e["volunteer_id"] for e in promo2["still_waiting"]] == [D]

    # 审计：两轮递补记录；第二轮名单顺序固化
    r = client.get(f"/api/trainings/batches/{batch_id}/promotions")
    rounds = r.json()
    assert len(rounds) == 2
    assert [x["volunteer_id"] for x in rounds[0]["entries"]] == [F, G]
    assert rounds[1]["promoted_count"] == 1

    # 候选人放弃：D 放弃候补后重新登记，seq 增大排到同梯队队尾（A 此时已退班，重新排队）
    r = client.post(f"/api/trainings/waitlist/{wd['id']}/decline",
                    json={"reason": "孩子暑期外出"})
    assert r.status_code == 200
    assert r.json()["promoted_count"] == 0  # 候补放弃不释放名额
    wd2 = register_wait(batch_id, D, 3, "普通登记，外出归来重新登记")
    wa = register_wait(batch_id, A, 3, "普通登记")
    queue = waitlist_ids(batch_id)
    assert [vid for vid, _ in queue] == [D, A]  # D 的新序号仍早于 A

    # 临时扩容 3→5：在班 E/F/G 三人，新增 2 个名额一次性递补 D、A
    r = client.post(f"/api/trainings/batches/{batch_id}/expand", json={"new_capacity": 5})
    assert r.status_code == 200, r.text
    promo3 = r.json()
    assert promo3["trigger"] == "临时扩容"
    assert promo3["seats_available"] == 2
    assert [p["volunteer_id"] for p in promo3["promoted"]] == [D, A]
    assert promo3["promoted_count"] == 2

    # 不能缩容
    r = client.post(f"/api/trainings/batches/{batch_id}/expand", json={"new_capacity": 4})
    assert r.status_code == 400

    # 入选后放弃：A 放弃名额 → B（优待）在候补则 B 入选
    wb = register_wait(batch_id, B, 1, "老学员补报优待")
    r = client.post(f"/api/trainings/waitlist/{wa['id']}/decline",
                    json={"reason": "家长改期"})
    assert r.status_code == 200, r.text
    promo4 = r.json()
    assert promo4["trigger"] == "候补放弃"
    assert promo4["seats_released"] == 1
    assert [p["volunteer_id"] for p in promo4["promoted"]] == [B]

    # 未送达也要可查
    r = client.post(f"/api/trainings/waitlist/{wb['id']}/notify",
                    json={"delivered": False, "detail": "电话无人接听，已短信"})
    assert "通知未送达" in r.json()["explanation"]

    # 期次详情含候补与空位统计
    detail = client.get(f"/api/trainings/batches/{batch_id}").json()
    assert detail["enrollment_count"] == 5  # E F G D B
    assert detail["waiting_count"] == 0
    assert detail["available_seats"] == 0


def test_batch_enroll_auto_waitlist():
    X, Y = make_volunteer("自动候补子"), make_volunteer("自动候补丑")
    batch_id = make_batch("小班体验课", 1)
    client.post("/api/trainings/enrollments/batch",
                json={"batch_id": batch_id, "volunteer_ids": [X]})
    r = client.post("/api/trainings/enrollments/batch", json={
        "batch_id": batch_id, "volunteer_ids": [Y],
        "enqueue_when_full": True, "priority_tier": 2, "priority_reason": "老学员",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["enrolled_count"] == 0 and body["waitlisted_count"] == 1
    queue = waitlist_ids(batch_id)
    assert queue[0][0] == Y and queue[0][1]["priority_label"] == "老学员/已完成讲解服务"

    # 不开自动候补时仍按“班额已满”拒绝
    Z = make_volunteer("自动候补寅")
    r = client.post("/api/trainings/enrollments/batch",
                    json={"batch_id": batch_id, "volunteer_ids": [Z]})
    assert any(s["reason"] == "班额已满" for s in r.json()["skipped"])
