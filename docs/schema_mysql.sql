-- ============================================================================
-- 校园生活平台 - MySQL 建表脚本（部署环境）
-- 由 backend/scripts/gen_schema_docs.py 依据 SQLAlchemy 模型自动生成
-- 数据库：school_life，字符集：utf8mb4
-- 执行：mysql -uroot -p < docs/schema_mysql.sql
-- ============================================================================

CREATE DATABASE IF NOT EXISTS `school_life` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE `school_life`;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE login_logs (
	user_id INTEGER COMMENT '用户ID（失败时可能为NULL）', 
	student_id VARCHAR(32) COMMENT '尝试登录的学号', 
	success TINYINT(1) NOT NULL COMMENT '是否成功', 
	message VARCHAR(255) COMMENT '结果说明', 
	ip VARCHAR(64) COMMENT '来源IP', 
	user_agent VARCHAR(255) COMMENT 'UA', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录日志';

CREATE INDEX ix_login_logs_success ON login_logs (success);

CREATE INDEX ix_login_logs_user_id ON login_logs (user_id);

CREATE INDEX ix_login_logs_student_id ON login_logs (student_id);

CREATE TABLE modules (
	code VARCHAR(64) NOT NULL COMMENT '模块标识（=posts.type）', 
	name VARCHAR(64) NOT NULL COMMENT '模块名称', 
	icon VARCHAR(64) COMMENT '图标名（前端 Element Plus 图标）', 
	description VARCHAR(255) COMMENT '模块简介', 
	sort_order INTEGER NOT NULL COMMENT '排序，越小越靠前', 
	enabled TINYINT(1) NOT NULL COMMENT '是否启用', 
	is_system TINYINT(1) NOT NULL COMMENT '系统内置模块不允许删除', 
	config TEXT COMMENT '模块配置(JSON)', 
	allow_roles VARCHAR(255) COMMENT '允许发布的角色，逗号分隔', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='功能模块定义（可后台启停 / 排序 / 新增）';

CREATE UNIQUE INDEX ix_modules_code ON modules (code);

CREATE TABLE operation_logs (
	user_id INTEGER COMMENT '操作人ID（未登录为NULL）', 
	username VARCHAR(64) COMMENT '操作人账号快照', 
	log_type VARCHAR(16) NOT NULL COMMENT '日志类型', 
	module VARCHAR(64) COMMENT '所属模块', 
	action VARCHAR(64) NOT NULL COMMENT '动作，例如 create / audit / ban', 
	target_type VARCHAR(32) COMMENT '目标类型', 
	target_id INTEGER COMMENT '目标ID', 
	detail TEXT COMMENT '详情(JSON 或文本)', 
	ip VARCHAR(64) COMMENT '来源IP', 
	user_agent VARCHAR(255) COMMENT 'UA', 
	duration_ms INTEGER COMMENT '耗时(毫秒)', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作日志';

CREATE INDEX ix_operation_logs_module ON operation_logs (module);

CREATE INDEX ix_operation_logs_log_type ON operation_logs (log_type);

CREATE INDEX ix_operation_logs_user_id ON operation_logs (user_id);

CREATE TABLE system_configs (
	`key` VARCHAR(64) NOT NULL COMMENT '配置键', 
	value TEXT COMMENT '配置值', 
	value_type VARCHAR(16) NOT NULL COMMENT '值类型：str/int/bool/json', 
	`group` VARCHAR(32) NOT NULL COMMENT '分组', 
	title VARCHAR(64) COMMENT '配置项名称', 
	description VARCHAR(255) COMMENT '说明', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统配置（键值对）';

CREATE UNIQUE INDEX ix_system_configs_key ON system_configs (`key`);

CREATE INDEX ix_system_configs_group ON system_configs (`group`);

CREATE TABLE users (
	username VARCHAR(64) NOT NULL COMMENT '登录名（默认=学号）', 
	password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希', 
	`role` VARCHAR(32) NOT NULL COMMENT '角色', 
	status VARCHAR(16) NOT NULL COMMENT '账号状态', 
	student_id VARCHAR(32) NOT NULL COMMENT '学号', 
	nickname VARCHAR(64) COMMENT '昵称', 
	avatar VARCHAR(255) COMMENT '头像地址', 
	email VARCHAR(128) COMMENT '邮箱（预留）', 
	phone VARCHAR(32) COMMENT '手机号（预留）', 
	ban_reason VARCHAR(255) COMMENT '封禁原因', 
	banned_at DATETIME COMMENT '封禁时间', 
	banned_by INTEGER COMMENT '封禁操作人ID', 
	last_login_at DATETIME COMMENT '最后登录时间', 
	last_login_ip VARCHAR(64) COMMENT '最后登录IP', 
	login_count INTEGER NOT NULL COMMENT '累计登录次数', 
	post_count INTEGER NOT NULL COMMENT '发帖计数（冗余，便于统计）', 
	remark VARCHAR(255) COMMENT '管理员备注', 
	handover_to_id INTEGER COMMENT '管理员权限拟移交给谁', 
	handover_at DATETIME COMMENT '移交发起时间（北京时间）', 
	handover_effective_at DATETIME COMMENT '移交生效时间（北京时间）', 
	handover_freeze_at DATETIME COMMENT '待上任冻结开始时间；非空即冻结中', 
	handover_prev_role VARCHAR(32) COMMENT '接管前的原角色，用于冻结期授权与撤销时恢复', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户（普通用户 / 内容审核员 / 管理员）';

CREATE INDEX ix_users_handover_to_id ON users (handover_to_id);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE UNIQUE INDEX ix_users_student_id ON users (student_id);

CREATE INDEX ix_users_status ON users (status);

CREATE INDEX ix_users_handover_freeze_at ON users (handover_freeze_at);

CREATE INDEX ix_users_role ON users (`role`);

CREATE INDEX ix_users_handover_effective_at ON users (handover_effective_at);

CREATE TABLE admin_module_access (
	user_id INTEGER NOT NULL COMMENT '管理员', 
	module_code VARCHAR(64) NOT NULL COMMENT '模块标识', 
	permission VARCHAR(32) NOT NULL COMMENT '权限：manage/audit/read', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_admin_module UNIQUE (user_id, module_code), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='管理员-模块授权（RBAC 预留，未启用）';

CREATE INDEX ix_admin_module_access_module_code ON admin_module_access (module_code);

CREATE INDEX ix_admin_module_access_user_id ON admin_module_access (user_id);

CREATE TABLE messages (
	sender_id INTEGER NOT NULL COMMENT '发送者', 
	receiver_id INTEGER NOT NULL COMMENT '接收者', 
	content TEXT NOT NULL COMMENT '文本内容（纯图片/语音时存空字符串，与数据库 NOT NULL 对齐）', 
	msg_type VARCHAR(16) NOT NULL COMMENT '消息类型', 
	media TEXT COMMENT '图片/语音/视频(JSON数组)', 
	is_read TINYINT(1) NOT NULL COMMENT '是否已读', 
	read_at DATETIME COMMENT '阅读时间', 
	conversation_key VARCHAR(64) COMMENT '会话键', 
	post_id INTEGER COMMENT '关联帖子ID', 
	sender_deleted TINYINT(1) NOT NULL COMMENT '发送方已删除', 
	receiver_deleted TINYINT(1) NOT NULL COMMENT '接收方已删除', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	FOREIGN KEY(sender_id) REFERENCES users (id), 
	FOREIGN KEY(receiver_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='站内私信';

CREATE INDEX ix_messages_receiver_id ON messages (receiver_id);

CREATE INDEX ix_messages_msg_type ON messages (msg_type);

CREATE INDEX ix_messages_is_read ON messages (is_read);

CREATE INDEX ix_messages_sender_id ON messages (sender_id);

CREATE INDEX ix_messages_conversation_key ON messages (conversation_key);

CREATE TABLE notifications (
	user_id INTEGER NOT NULL COMMENT '接收人', 
	type VARCHAR(32) NOT NULL COMMENT '通知类型', 
	title VARCHAR(128) NOT NULL COMMENT '标题', 
	content TEXT COMMENT '内容', 
	is_read TINYINT(1) NOT NULL COMMENT '是否已读', 
	read_at DATETIME COMMENT '阅读时间', 
	link VARCHAR(255) COMMENT '跳转信息(JSON)', 
	ref_id INTEGER COMMENT '关联业务ID', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='站内通知';

CREATE INDEX ix_notifications_type ON notifications (type);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE INDEX ix_notifications_is_read ON notifications (is_read);

CREATE TABLE posts (
	type VARCHAR(64) NOT NULL COMMENT '模块标识，对应 modules.code', 
	user_id INTEGER NOT NULL COMMENT '发布者', 
	title VARCHAR(128) COMMENT '标题（选填）', 
	content TEXT COMMENT '描述（选填）', 
	media TEXT COMMENT '图片/视频(JSON数组)', 
	location VARCHAR(128) COMMENT '地点（选填）', 
	happened_at DATETIME COMMENT '发生时间（选填）', 
	contact VARCHAR(128) NOT NULL COMMENT '联系方式（必填，公开可见）', 
	status VARCHAR(16) NOT NULL COMMENT '业务状态', 
	audit_status VARCHAR(16) NOT NULL COMMENT '审核状态', 
	audit_remark VARCHAR(255) COMMENT '审核意见', 
	audited_by INTEGER COMMENT '审核人', 
	audited_at DATETIME COMMENT '审核时间', 
	assignee_id INTEGER COMMENT '当前指派/认领的审核员ID', 
	assigned_by INTEGER COMMENT '指派人ID', 
	assigned_at DATETIME COMMENT '指派/认领时间', 
	assignment_expires_at DATETIME COMMENT '认领到期时间（超时自动退回公共池）', 
	is_top TINYINT(1) NOT NULL COMMENT '是否置顶', 
	view_count INTEGER NOT NULL COMMENT '浏览量', 
	comment_count INTEGER NOT NULL COMMENT '评论数（含楼中楼回复）', 
	favorite_count INTEGER NOT NULL COMMENT '收藏数', 
	like_count INTEGER NOT NULL COMMENT '点赞数', 
	is_deleted TINYINT(1) NOT NULL COMMENT '是否已删除(软删除)', 
	deleted_at DATETIME COMMENT '删除时间', 
	deleted_by INTEGER COMMENT '删除人', 
	ext_json TEXT COMMENT '模块扩展字段(JSON)', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='帖子（所有模块统一存储，type 区分模块；含审核指派字段）';

CREATE INDEX ix_posts_type ON posts (type);

CREATE INDEX ix_posts_is_top ON posts (is_top);

CREATE INDEX ix_posts_type_status_deleted ON posts (type, status, is_deleted);

CREATE INDEX ix_posts_status ON posts (status);

CREATE INDEX ix_posts_is_deleted ON posts (is_deleted);

CREATE INDEX ix_posts_audit_status ON posts (audit_status);

CREATE INDEX ix_posts_audit_assignee ON posts (audit_status, assignee_id);

CREATE INDEX ix_posts_assignee_id ON posts (assignee_id);

CREATE INDEX ix_posts_audit_created ON posts (audit_status, created_at);

CREATE INDEX ix_posts_assignment_expires_at ON posts (assignment_expires_at);

CREATE INDEX ix_posts_user_id ON posts (user_id);

CREATE TABLE upload_files (
	user_id INTEGER COMMENT '上传者', 
	filename VARCHAR(255) NOT NULL COMMENT '存储文件名', 
	original_name VARCHAR(255) COMMENT '原始文件名', 
	path VARCHAR(255) NOT NULL COMMENT '相对路径', 
	url VARCHAR(255) NOT NULL COMMENT '访问地址', 
	mime VARCHAR(64) COMMENT 'MIME 类型', 
	media_type VARCHAR(16) NOT NULL COMMENT 'image / video / audio', 
	size INTEGER NOT NULL COMMENT '字节数', 
	post_id INTEGER COMMENT '关联帖子ID（兼容保留）', 
	owner_type VARCHAR(16) COMMENT '归属类型', 
	owner_id INTEGER COMMENT '归属记录ID', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上传文件记录';

CREATE INDEX ix_upload_files_owner_type ON upload_files (owner_type);

CREATE INDEX ix_upload_files_owner_id ON upload_files (owner_id);

CREATE INDEX ix_upload_owner ON upload_files (owner_type, owner_id);

CREATE INDEX ix_upload_files_user_id ON upload_files (user_id);

CREATE INDEX ix_upload_files_post_id ON upload_files (post_id);

CREATE TABLE comments (
	post_id INTEGER NOT NULL COMMENT '帖子ID', 
	user_id INTEGER NOT NULL COMMENT '评论人', 
	parent_id INTEGER COMMENT '父评论ID（直接上级）', 
	root_id INTEGER COMMENT '顶级评论ID（楼中楼）', 
	content TEXT NOT NULL COMMENT '评论内容（纯图片/语音评论存空字符串，避免 NULL）', 
	media TEXT COMMENT '图片/视频/语音(JSON数组)', 
	reply_to_user_id INTEGER COMMENT '被回复的用户ID', 
	like_count INTEGER NOT NULL COMMENT '点赞数', 
	reply_count INTEGER NOT NULL COMMENT '直接回复数（冗余计数）', 
	is_deleted TINYINT(1) NOT NULL COMMENT '软删除', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(parent_id) REFERENCES comments (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='帖子评论';

CREATE INDEX ix_comments_post_id ON comments (post_id);

CREATE INDEX ix_comments_root_id ON comments (root_id);

CREATE INDEX ix_comments_user_id ON comments (user_id);

CREATE INDEX ix_comments_parent_id ON comments (parent_id);

CREATE INDEX ix_comments_reply_to_user_id ON comments (reply_to_user_id);

CREATE INDEX ix_comments_is_deleted ON comments (is_deleted);

CREATE TABLE favorites (
	user_id INTEGER NOT NULL COMMENT '用户', 
	post_id INTEGER NOT NULL COMMENT '帖子', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_favorite_user_post UNIQUE (user_id, post_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='收藏';

CREATE INDEX ix_favorites_post_id ON favorites (post_id);

CREATE INDEX ix_favorites_user_id ON favorites (user_id);

CREATE TABLE post_audit_logs (
	post_id INTEGER NOT NULL COMMENT '帖子ID', 
	action VARCHAR(16) NOT NULL COMMENT 'assign/claim/release/approve/reject', 
	actor_id INTEGER COMMENT '操作人ID', 
	assignee_id INTEGER COMMENT '被指派/认领的审核员ID', 
	assign_source VARCHAR(16) COMMENT 'admin/self', 
	remark VARCHAR(255) COMMENT '备注（审核意见 / 改派说明）', 
	duration_ms INTEGER COMMENT '处理耗时(毫秒)', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审核流水（指派 / 认领 / 退回 / 通过 / 拒绝）';

CREATE INDEX ix_post_audit_logs_actor_id ON post_audit_logs (actor_id);

CREATE INDEX ix_post_audit_logs_post_id ON post_audit_logs (post_id);

CREATE INDEX ix_post_audit_logs_assignee_id ON post_audit_logs (assignee_id);

CREATE INDEX ix_post_audit_logs_post_action ON post_audit_logs (post_id, action);

CREATE TABLE post_likes (
	user_id INTEGER NOT NULL COMMENT '点赞人', 
	post_id INTEGER NOT NULL COMMENT '帖子', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_post_like_user_post UNIQUE (user_id, post_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='帖子点赞';

CREATE INDEX ix_post_likes_user_id ON post_likes (user_id);

CREATE INDEX ix_post_likes_post_id ON post_likes (post_id);

CREATE TABLE reports (
	reporter_id INTEGER NOT NULL COMMENT '举报人', 
	post_id INTEGER COMMENT '被举报帖子', 
	target_user_id INTEGER COMMENT '被举报用户（举报用户时）', 
	reason VARCHAR(255) NOT NULL COMMENT '举报原因', 
	detail TEXT COMMENT '补充说明', 
	status VARCHAR(16) NOT NULL COMMENT '处理状态', 
	handled_by INTEGER COMMENT '处理人', 
	handled_at DATETIME COMMENT '处理时间', 
	handle_remark VARCHAR(255) COMMENT '处理意见', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	FOREIGN KEY(reporter_id) REFERENCES users (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='举报';

CREATE INDEX ix_reports_reporter_id ON reports (reporter_id);

CREATE INDEX ix_reports_target_user_id ON reports (target_user_id);

CREATE INDEX ix_reports_status ON reports (status);

CREATE INDEX ix_reports_post_id ON reports (post_id);

CREATE TABLE comment_likes (
	user_id INTEGER NOT NULL COMMENT '点赞人', 
	comment_id INTEGER NOT NULL COMMENT '评论', 
	id INTEGER NOT NULL AUTO_INCREMENT COMMENT '主键', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_comment_like_user_comment UNIQUE (user_id, comment_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(comment_id) REFERENCES comments (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='评论点赞';

CREATE INDEX ix_comment_likes_comment_id ON comment_likes (comment_id);

CREATE INDEX ix_comment_likes_user_id ON comment_likes (user_id);

SET FOREIGN_KEY_CHECKS = 1;
