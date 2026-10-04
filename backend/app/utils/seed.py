# -*- coding: utf-8 -*-
"""演示数据生成（flask seed / flask seed --reset）。

用途：
1. 答辩演示时快速铺满列表、审核台、回收站、日志；
2. 前端联调时不必手动造数据。

数据是「确定性」的（固定随机种子），每次生成结果一致，方便复现问题。
"""

import json
import random
from datetime import datetime, timedelta

from ..extensions import db
from ..models import (
    AdminModuleAccess,
    Comment,
    CommentLike,
    Favorite,
    LoginLog,
    Message,
    Module,
    Notification,
    OperationLog,
    Post,
    PostLike,
    Report,
    SystemConfig,
    UploadFile,
    User,
)
from ..utils.config_service import init_default_configs
from ..utils.constants import (
    AUDIT_APPROVED,
    AUDIT_PENDING,
    AUDIT_REJECTED,
    MODULE_DAILY,
    MODULE_ERRAND,
    MODULE_GROUP_BUY,
    MODULE_LOST_FOUND,
    MODULE_SECOND_HAND,
    POST_CLAIMED,
    POST_CLOSED,
    POST_EXPIRED,
    POST_ONGOING,
    REPORT_PENDING,
    ROLE_ADMIN,
    ROLE_USER,
    STATUS_ACTIVE,
    STATUS_BANNED,
)
from ..models.module import default_modules
from .constants import LOG_TYPE_OPERATION

RANDOM_SEED = 20240601

# ---------------------------------------------------------------------------
# 文案素材
# ---------------------------------------------------------------------------
LOST_TITLES = [
    ('在图书馆三楼丢了黑色雨伞', '昨天下午在图书馆三楼自习，走的时候把一把黑色长柄雨伞落在座位上了，伞柄有个小熊挂件。'),
    ('二食堂捡到校园卡一张', '在二食堂二楼靠窗的位置捡到一张校园卡，姓名是张**，已交到二食堂服务台。'),
    ('丢失 AirPods 右耳一只', '在操场跑步时掉的，充电盒还在，只有右耳丢了，捡到的同学麻烦联系我。'),
    ('捡到一副黑框眼镜', '在教学楼 B203 教室最后一排捡到，镜片有一点划痕，已放在教室讲台抽屉里。'),
    ('丢失蓝色保温杯', '杯身贴了社团的贴纸，杯盖有一点掉漆，在体育馆篮球场附近丢的。'),
    ('捡到一本考研数学笔记本', '在图书馆一楼自习区捡到，封面写着「2025 考研加油」，笔记很详细，失主应该很着急。'),
    ('丢失学生证', '今天上午从宿舍去教学楼路上丢的，学院是计算机学院，如果捡到请联系我，非常感谢。'),
    ('在快递站捡到一个黑色背包', '背包里有几本书和一个充电宝，已经交到快递站工作人员那里了。'),
    ('丢失一把宿舍钥匙', '钥匙上有一个黄色小鸭子挂件，可能掉在宿舍楼下或者洗衣房了。'),
    ('捡到一张银行卡', '在 ATM 机旁边捡到的，已经交给银行柜台，如果着急可以去问一下。'),
    ('丢失粉色充电宝', '在图书馆四楼充电时落下的，上面贴了猫咪贴纸。'),
    ('捡到一把尤克里里', '在社团活动室捡到的，琴包上有手写名字，请失主联系我认领。'),
    ('丢失身份证（已找回，谢谢大家）', '之前发的寻物信息，身份证已经找回来了，感谢帮忙转发的同学。'),
    ('丢失一副白色耳机', '在篮球场边上休息时放在长椅上忘记拿了。'),
    ('捡到学生卡与一串钥匙', '在校门口共享单车车筐里捡到的，已交保卫处。'),
]

CONTACTS = ['微信: xiaoming2021', 'QQ: 38291047', '电话 13800001111',
            '微信同号 13900002222', 'QQ 7749201', '邮箱 dorm204@example.com']

LOCATIONS = ['图书馆三楼', '二食堂二楼', '东操场', '教学楼 B203', '体育馆篮球场',
             '宿舍 6 号楼', '快递站', '校门口', '社团活动室', 'ATM 机旁']

NICKNAMES = ['小明', '阿May', '老王', '清晨的风', '夜跑选手', '考研狗', '小面包',
             '图书馆钉子户', '宿舍总管', '食堂探险家', '社团打工人', '爱丢东西的人']


def _users():
    """生成 1 管理员 + 12 学生。"""
    admin = User(student_id='admin', username='admin', nickname='系统管理员',
                 role=ROLE_ADMIN, status=STATUS_ACTIVE, email='admin@example.com')
    admin.set_password('admin123')

    students = []
    for index in range(12):
        student_id = f'2021{index + 1:04d}'
        user = User(
            student_id=student_id,
            username=student_id,
            nickname=NICKNAMES[index % len(NICKNAMES)],
            role=ROLE_USER,
            status=STATUS_BANNED if index == 11 else STATUS_ACTIVE,
            ban_reason='多次发布广告信息' if index == 11 else None,
        )
        user.set_password('123456')
        if index == 11:
            user.banned_at = datetime.now() - timedelta(days=2)
        students.append(user)
    return admin, students


def _clear_business_data():
    """清空业务数据（保留表结构）。"""
    for model in (Message, PostLike, CommentLike, Favorite, Comment, Report,
                  Notification, AdminModuleAccess, UploadFile, OperationLog,
                  LoginLog, Post, User, Module, SystemConfig):
        model.query.delete()
    db.session.commit()


def run_seed(reset=False):
    """执行数据生成。

    :param reset: True 时先清空业务数据再生成，结果确定、可重复执行。

    非 reset 模式下若库里已有业务数据，直接跳过并返回说明——
    否则重复执行会撞 favorites 等表的唯一约束（这是脚本不可重复执行的成因）。
    """
    rnd = random.Random(RANDOM_SEED)

    existing_posts = Post.query.count()
    existing_users = User.query.count()
    if not reset and (existing_posts > 0 or existing_users > 0):
        return {
            'skipped': True,
            'reason': '库中已有业务数据，未重复生成（需要重建请加 --reset）',
            'users': existing_users,
            'posts': existing_posts,
        }

    if reset:
        _clear_business_data()

    # ---- 模块 ----
    created_modules = 0
    for item in default_modules():
        if Module.query.filter_by(code=item['code']).first():
            continue
        db.session.add(Module(**item))
        created_modules += 1
    # 「其他」模块：演示后台新增模块的能力
    if not Module.query.filter_by(code='other').first():
        db.session.add(Module(code='other', name='其他', icon='MoreFilled',
                              description='其他校园生活互助信息', sort_order=50, enabled=True))
        created_modules += 1
    db.session.commit()

    # ---- 配置 ----
    init_default_configs()

    # ---- 用户 ----
    admin, students = _users()
    if not User.query.filter_by(student_id=admin.student_id).first():
        db.session.add(admin)
    else:
        admin = User.query.filter_by(student_id=admin.student_id).first()
    for user in students:
        if not User.query.filter_by(student_id=user.student_id).first():
            db.session.add(user)
    db.session.commit()
    students = User.query.filter(User.student_id != 'admin').order_by(User.id.asc()).all()

    # ---- 帖子 ----
    now = datetime.now()
    statuses_plan = (
        [POST_ONGOING] * 8 + [POST_CLAIMED] * 2 + [POST_EXPIRED] * 1 + [POST_CLOSED] * 1
    )
    audits_plan = (
        [AUDIT_APPROVED] * 8 + [AUDIT_PENDING] * 3 + [AUDIT_REJECTED] * 1
    )
    posts = []
    for index, (title, content) in enumerate(LOST_TITLES):
        author = students[index % len(students)]
        status = statuses_plan[index % len(statuses_plan)]
        audit = audits_plan[index % len(audits_plan)]
        post = Post(
            type=MODULE_LOST_FOUND,
            user_id=author.id,
            title=title,
            content=content,
            location=rnd.choice(LOCATIONS),
            happened_at=now - timedelta(days=rnd.randint(1, 20), hours=rnd.randint(0, 20)),
            contact=rnd.choice(CONTACTS),
            status=status,
            audit_status=audit,
            audit_remark='内容不符合平台规范，请补充物品特征' if audit == AUDIT_REJECTED else None,
            view_count=rnd.randint(5, 320),
            is_top=index == 0,
            created_at=now - timedelta(days=rnd.randint(0, 15), hours=rnd.randint(0, 23)),
        )
        if audit == AUDIT_APPROVED:
            post.audited_by = admin.id
            post.audited_at = post.created_at + timedelta(hours=2)
        db.session.add(post)
        posts.append(post)

    # ---- 二手交易演示数据：验证 ext_json 真实落库与回读 ----
    second_hand_items = [
        ('出九成新自行车', '骑了半年，平时都停宿舍楼下，刹车刚保养过。',
         {'price': 260, 'original_price': 480, 'condition': '九成新', 'trade_type': '面交'}),
        ('出闲置台灯', '毕业搬宿舍带不走，三档亮度，功能一切正常。',
         {'price': 25, 'original_price': 59, 'condition': '八成新', 'trade_type': '面交'}),
        ('收一个二手键盘', '想收一把 87 键机械键盘，能正常使用就行，价格好商量。',
         {'price': 80, 'condition': '不限', 'trade_type': '都可以'}),
    ]
    for index, (title, content, ext) in enumerate(second_hand_items):
        author = students[(index + 3) % len(students)]
        post = Post(
            type=MODULE_SECOND_HAND,
            user_id=author.id,
            title=title,
            content=content,
            ext_json=json.dumps(ext, ensure_ascii=False),
            happened_at=now + timedelta(days=index + 1, hours=10),
            location=rnd.choice(LOCATIONS),
            contact=rnd.choice(CONTACTS),
            status=POST_ONGOING,
            audit_status=AUDIT_APPROVED,
            audited_by=admin.id,
            audited_at=now - timedelta(hours=rnd.randint(2, 30)),
            view_count=rnd.randint(5, 120),
            created_at=now - timedelta(days=rnd.randint(0, 6), hours=rnd.randint(0, 20)),
        )
        db.session.add(post)
        posts.append(post)

    # ---- v1.5 三模块演示数据：ext_json / 通用字段各验证一遍 ----
    group_buy_post = Post(
        type=MODULE_GROUP_BUY,
        user_id=students[2].id,
        title='拼奶茶（一点点，满 5 杯起送）',
        content='6 号宿舍楼下自取，按人头分摊，口味群里说。',
        ext_json=json.dumps({'target_count': 5, 'current_count': 2,
                             'start_date': (now + timedelta(days=2)).strftime('%Y-%m-%d')},
                            ensure_ascii=False),
        location='6 号宿舍楼下',
        contact='微信 groupbuy_demo',
        status=POST_ONGOING,
        audit_status=AUDIT_APPROVED,
        audited_by=admin.id,
        audited_at=now - timedelta(hours=5),
        view_count=rnd.randint(20, 80),
        created_at=now - timedelta(hours=6),
    )
    errand_post = Post(
        type=MODULE_ERRAND,
        user_id=students[4].id,
        title='帮取一个快递（菜鸟驿站  6 号楼）',
        content='小件，不重；送到 6 号楼 302 即可，费用可以商量。',
        location='菜鸟驿站',
        contact='微信 errand_demo',
        happened_at=now + timedelta(hours=6),
        status=POST_ONGOING,
        audit_status=AUDIT_APPROVED,
        audited_by=admin.id,
        audited_at=now - timedelta(hours=3),
        view_count=rnd.randint(10, 60),
        created_at=now - timedelta(hours=4),
    )
    daily_post = Post(
        type=MODULE_DAILY,
        user_id=students[5].id,
        title='食堂新出的麻辣香锅挺好吃',
        content='就在二食堂二楼，微辣刚好，推荐加宽粉。',
        location='二食堂二楼',
        contact='',
        status=POST_ONGOING,
        audit_status=AUDIT_APPROVED,
        audited_by=admin.id,
        audited_at=now - timedelta(hours=2),
        view_count=rnd.randint(5, 40),
        created_at=now - timedelta(hours=2),
    )
    for post in (group_buy_post, errand_post, daily_post):
        db.session.add(post)
        posts.append(post)

    # 一条软删除帖子 → 回收站演示
    recycled = Post(
        type=MODULE_LOST_FOUND, user_id=students[2].id, title='【已删除】测试违规信息',
        content='这条记录用于演示回收站功能。', contact='微信: test', status=POST_ONGOING,
        audit_status=AUDIT_APPROVED, is_deleted=True,
        deleted_at=now - timedelta(days=1), deleted_by=admin.id,
    )
    db.session.add(recycled)
    db.session.commit()
    posts = Post.query.filter_by(is_deleted=False).all()

    # ---- 评论 / 收藏 / 举报 ----
    comment_texts = ['这个我好像见过，帮你转发一下～', '已经交到服务台了，可以去看看。',
                     '顶一下，希望失主早点找到。', '我也是在那附近丢过东西，注意安全。']
    for post in posts[:6]:
        for text in rnd.sample(comment_texts, rnd.randint(1, 2)):
            commenter = rnd.choice(students)
            db.session.add(Comment(post_id=post.id, user_id=commenter.id, content=text,
                                   created_at=post.created_at + timedelta(hours=3)))
            post.comment_count = (post.comment_count or 0) + 1
    for post in posts[:5]:
        # 防御：跳过已存在的 (user, post) 组合，避免 UNIQUE(user_id, post_id) 冲突
        student = rnd.choice(students)
        if Favorite.query.filter_by(user_id=student.id, post_id=post.id).first():
            continue
        db.session.add(Favorite(user_id=student.id, post_id=post.id))
        post.favorite_count = (post.favorite_count or 0) + 1
    db.session.add(Report(reporter_id=students[1].id, post_id=posts[1].id,
                          reason='虚假信息', detail='感觉是广告，请管理员核实', status=REPORT_PENDING))
    db.session.add(Report(reporter_id=students[3].id, post_id=posts[4].id,
                          reason='联系方式不实', status=REPORT_PENDING))
    db.session.commit()

    # ---- 通知 ----
    for post in posts[:4]:
        db.session.add(Notification(user_id=post.user_id, type='audit', title='你的信息已通过审核',
                                    content=f'《{post.title}》已公开展示。', is_read=False,
                                    ref_id=post.id))
    db.session.add(Notification(user_id=students[0].id, type='system', title='欢迎使用校园生活平台',
                                content='请勿上传身份证、银行卡等敏感信息。', is_read=False))
    db.session.commit()

    # ---- 日志 ----
    actions = ['login', 'create', 'update', 'audit', 'delete', 'ban']
    for index in range(30):
        user = rnd.choice(students + [admin])
        db.session.add(OperationLog(
            user_id=user.id, username=user.student_id, log_type=LOG_TYPE_OPERATION,
            module=rnd.choice([MODULE_LOST_FOUND, 'auth', 'users', 'posts']),
            action=rnd.choice(actions), target_type='post',
            target_id=rnd.choice(posts).id if posts else None,
            ip=f'192.168.1.{rnd.randint(2, 250)}',
            created_at=now - timedelta(hours=rnd.randint(1, 200)),
        ))
    for index in range(25):
        user = rnd.choice(students + [admin])
        success_flag = rnd.random() > 0.2
        db.session.add(LoginLog(
            user_id=user.id if success_flag else None,
            student_id=user.student_id if success_flag else '20210099',
            success=success_flag,
            message='登录成功' if success_flag else '账号或密码错误',
            ip=f'192.168.1.{rnd.randint(2, 250)}',
            created_at=now - timedelta(hours=rnd.randint(1, 200)),
        ))
    db.session.commit()

    # ---- 统计字段回填 ----
    for user in User.query.all():
        user.post_count = Post.query.filter_by(user_id=user.id, is_deleted=False).count()
    db.session.commit()

    return {
        'modules_created': created_modules,
        'users': User.query.count(),
        'posts': Post.query.count(),
        'comments': Comment.query.count(),
        'reports': Report.query.count(),
        'logs': OperationLog.query.count() + LoginLog.query.count(),
        'accounts': {'admin': 'admin / admin123', 'student': '20210001 / 123456'},
    }


__all__ = ['run_seed']
