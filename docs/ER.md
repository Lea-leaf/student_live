# 数据库 ER 图

> 本文件由 `backend/scripts/gen_schema_docs.py` 从模型自动生成，改模型后重新执行即可同步。
> 在支持 Mermaid 的编辑器（VS Code / Typora / Gitee / GitHub）中可直接渲染。

```mermaid
erDiagram
    %% 登录日志
    login_logs {
        INTEGER user_id null
        VARCHAR student_id null
        BOOLEAN success not_null
        VARCHAR message null
        VARCHAR ip null
        VARCHAR user_agent null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 功能模块定义（可后台启停 / 排序 / 新增）
    modules {
        VARCHAR code not_null
        VARCHAR name not_null
        VARCHAR icon null
        VARCHAR description null
        INTEGER sort_order not_null
        BOOLEAN enabled not_null
        BOOLEAN is_system not_null
        TEXT config null
        VARCHAR allow_roles null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 操作日志
    operation_logs {
        INTEGER user_id null
        VARCHAR username null
        VARCHAR log_type not_null
        VARCHAR module null
        VARCHAR action not_null
        VARCHAR target_type null
        INTEGER target_id null
        TEXT detail null
        VARCHAR ip null
        VARCHAR user_agent null
        INTEGER duration_ms null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 系统配置（键值对）
    system_configs {
        VARCHAR key not_null
        TEXT value null
        VARCHAR value_type not_null
        VARCHAR group not_null
        VARCHAR title null
        VARCHAR description null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 用户（普通用户 / 内容审核员 / 管理员）
    users {
        VARCHAR username not_null
        VARCHAR password_hash not_null
        VARCHAR role not_null
        VARCHAR status not_null
        VARCHAR student_id not_null
        VARCHAR nickname null
        VARCHAR avatar null
        VARCHAR email null
        VARCHAR phone null
        VARCHAR ban_reason null
        DATETIME banned_at null
        INTEGER banned_by null
        DATETIME last_login_at null
        VARCHAR last_login_ip null
        INTEGER login_count not_null
        INTEGER post_count not_null
        VARCHAR remark null
        INTEGER handover_to_id null
        DATETIME handover_at null
        DATETIME handover_effective_at null
        DATETIME handover_freeze_at null
        VARCHAR handover_prev_role null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 管理员-模块授权（RBAC 预留，未启用）
    admin_module_access {
        INTEGER user_id not_null FK
        VARCHAR module_code not_null
        VARCHAR permission not_null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 站内私信
    messages {
        INTEGER sender_id not_null FK
        INTEGER receiver_id not_null FK
        TEXT content not_null
        VARCHAR msg_type not_null
        TEXT media null
        BOOLEAN is_read not_null
        DATETIME read_at null
        VARCHAR conversation_key null
        INTEGER post_id null
        BOOLEAN sender_deleted not_null
        BOOLEAN receiver_deleted not_null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 站内通知
    notifications {
        INTEGER user_id not_null FK
        VARCHAR type not_null
        VARCHAR title not_null
        TEXT content null
        BOOLEAN is_read not_null
        DATETIME read_at null
        VARCHAR link null
        INTEGER ref_id null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 帖子（所有模块统一存储，type 区分模块；含审核指派字段）
    posts {
        VARCHAR type not_null
        INTEGER user_id not_null FK
        VARCHAR title null
        TEXT content null
        TEXT media null
        VARCHAR location null
        DATETIME happened_at null
        VARCHAR contact not_null
        VARCHAR status not_null
        VARCHAR audit_status not_null
        VARCHAR audit_remark null
        INTEGER audited_by null
        DATETIME audited_at null
        INTEGER assignee_id null
        INTEGER assigned_by null
        DATETIME assigned_at null
        DATETIME assignment_expires_at null
        BOOLEAN is_top not_null
        INTEGER view_count not_null
        INTEGER comment_count not_null
        INTEGER favorite_count not_null
        INTEGER like_count not_null
        BOOLEAN is_deleted not_null
        DATETIME deleted_at null
        INTEGER deleted_by null
        TEXT ext_json null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 上传文件记录
    upload_files {
        INTEGER user_id null FK
        VARCHAR filename not_null
        VARCHAR original_name null
        VARCHAR path not_null
        VARCHAR url not_null
        VARCHAR mime null
        VARCHAR media_type not_null
        INTEGER size not_null
        INTEGER post_id null
        VARCHAR owner_type null
        INTEGER owner_id null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 帖子评论
    comments {
        INTEGER post_id not_null FK
        INTEGER user_id not_null FK
        INTEGER parent_id null FK
        INTEGER root_id null
        TEXT content not_null
        TEXT media null
        INTEGER reply_to_user_id null
        INTEGER like_count not_null
        INTEGER reply_count not_null
        BOOLEAN is_deleted not_null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 收藏
    favorites {
        INTEGER user_id not_null FK
        INTEGER post_id not_null FK
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 审核流水（指派 / 认领 / 退回 / 通过 / 拒绝）
    post_audit_logs {
        INTEGER post_id not_null FK
        VARCHAR action not_null
        INTEGER actor_id null
        INTEGER assignee_id null
        VARCHAR assign_source null
        VARCHAR remark null
        INTEGER duration_ms null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 帖子点赞
    post_likes {
        INTEGER user_id not_null FK
        INTEGER post_id not_null FK
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 举报
    reports {
        INTEGER reporter_id not_null FK
        INTEGER post_id null FK
        INTEGER target_user_id null
        VARCHAR reason not_null
        TEXT detail null
        VARCHAR status not_null
        INTEGER handled_by null
        DATETIME handled_at null
        VARCHAR handle_remark null
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }
    %% 评论点赞
    comment_likes {
        INTEGER user_id not_null FK
        INTEGER comment_id not_null FK
        INTEGER id not_null PK
        DATETIME created_at not_null
        DATETIME updated_at not_null
    }

    %% 关系
    users ||--o{ admin_module_access : "user_id → id"
    users ||--o{ messages : "sender_id → id"
    users ||--o{ messages : "receiver_id → id"
    users ||--o{ notifications : "user_id → id"
    users ||--o{ posts : "user_id → id"
    users ||--o{ upload_files : "user_id → id"
    users ||--o{ comments : "user_id → id"
    posts ||--o{ comments : "post_id → id"
    comments ||--o{ comments : "parent_id → id"
    users ||--o{ favorites : "user_id → id"
    posts ||--o{ favorites : "post_id → id"
    posts ||--o{ post_audit_logs : "post_id → id"
    posts ||--o{ post_likes : "post_id → id"
    users ||--o{ post_likes : "user_id → id"
    posts ||--o{ reports : "post_id → id"
    users ||--o{ reports : "reporter_id → id"
    users ||--o{ comment_likes : "user_id → id"
    comments ||--o{ comment_likes : "comment_id → id"
```

## 表清单

| 表名 | 说明 | 字段数 |
|---|---|---|
| `login_logs` | 登录日志 | 9 |
| `modules` | 功能模块定义（可后台启停 / 排序 / 新增） | 12 |
| `operation_logs` | 操作日志 | 14 |
| `system_configs` | 系统配置（键值对） | 9 |
| `users` | 用户（普通用户 / 内容审核员 / 管理员） | 25 |
| `admin_module_access` | 管理员-模块授权（RBAC 预留，未启用） | 6 |
| `messages` | 站内私信 | 14 |
| `notifications` | 站内通知 | 11 |
| `posts` | 帖子（所有模块统一存储，type 区分模块；含审核指派字段） | 29 |
| `upload_files` | 上传文件记录 | 14 |
| `comments` | 帖子评论 | 13 |
| `favorites` | 收藏 | 5 |
| `post_audit_logs` | 审核流水（指派 / 认领 / 退回 / 通过 / 拒绝） | 10 |
| `post_likes` | 帖子点赞 | 5 |
| `reports` | 举报 | 12 |
| `comment_likes` | 评论点赞 | 5 |
