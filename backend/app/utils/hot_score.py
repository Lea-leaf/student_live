# -*- coding: utf-8 -*-
"""帖子热度评分（hot 排序）。

热度算法（答辩可讲的设计点）：

    基础分 = 浏览数 + 评论数3 + 点赞数2 + 收藏数2
    热度   = 基础分 / (1 + 发帖时长(小时) / 24)

- 浏览是最弱信号，评论代表讨论度，点赞/收藏代表认可度，因此权重更高；
- 时间衰减采用「每过 24 小时热度约减半」的简单模型，让新内容有曝光机会；
- 锚点时间优先用 `happened_at`（事情发生时间），没有则用 `created_at`；
- 置顶仍然优先于热度分，由排序调用方在外层先按 `is_top` 排序。
"""

from datetime import datetime

#: 互动权重（可按运营需要调整）
HOT_VIEW_WEIGHT = 1
HOT_COMMENT_WEIGHT = 3
HOT_LIKE_WEIGHT = 2
HOT_FAVORITE_WEIGHT = 2
#: 时间衰减窗口：24 小时
HOT_DECAY_HOURS = 24.0


def hot_score(post, now=None):
    """计算一条帖子的热度分（不修改数据库）。"""
    now = now or datetime.now()
    views = max(int(post.view_count or 0), 0)
    comments = max(int(post.comment_count or 0), 0)
    likes = max(int(post.like_count or 0), 0)
    favorites = max(int(post.favorite_count or 0), 0)

    base = (
        views * HOT_VIEW_WEIGHT
        + comments * HOT_COMMENT_WEIGHT
        + likes * HOT_LIKE_WEIGHT
        + favorites * HOT_FAVORITE_WEIGHT
    )

    anchor = post.happened_at or post.created_at
    if anchor:
        age_hours = max((now - anchor).total_seconds() / 3600.0, 0.0)
    else:
        age_hours = 0.0

    return round(base / (1.0 + age_hours / HOT_DECAY_HOURS), 4)


__all__ = [
    'hot_score',
    'HOT_VIEW_WEIGHT', 'HOT_COMMENT_WEIGHT', 'HOT_LIKE_WEIGHT', 'HOT_FAVORITE_WEIGHT',
    'HOT_DECAY_HOURS',
]