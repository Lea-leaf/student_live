-- ============================================================================
-- 校园生活平台 - SQLite 建表脚本（开发环境，与 flask db upgrade 等价）
-- 由 backend/scripts/gen_schema_docs.py 自动生成
-- ============================================================================

-- 登录日志
CREATE TABLE login_logs (
	user_id INTEGER, 
	student_id VARCHAR(32), 
	success BOOLEAN NOT NULL, 
	message VARCHAR(255), 
	ip VARCHAR(64), 
	user_agent VARCHAR(255), 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_login_logs_success ON login_logs (success);

CREATE INDEX ix_login_logs_user_id ON login_logs (user_id);

CREATE INDEX ix_login_logs_student_id ON login_logs (student_id);

-- 功能模块定义（可后台启停 / 排序 / 新增）
CREATE TABLE modules (
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	icon VARCHAR(64), 
	description VARCHAR(255), 
	sort_order INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	is_system BOOLEAN NOT NULL, 
	config TEXT, 
	allow_roles VARCHAR(255), 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_modules_code ON modules (code);

-- 操作日志
CREATE TABLE operation_logs (
	user_id INTEGER, 
	username VARCHAR(64), 
	log_type VARCHAR(16) NOT NULL, 
	module VARCHAR(64), 
	action VARCHAR(64) NOT NULL, 
	target_type VARCHAR(32), 
	target_id INTEGER, 
	detail TEXT, 
	ip VARCHAR(64), 
	user_agent VARCHAR(255), 
	duration_ms INTEGER, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_operation_logs_module ON operation_logs (module);

CREATE INDEX ix_operation_logs_log_type ON operation_logs (log_type);

CREATE INDEX ix_operation_logs_user_id ON operation_logs (user_id);

-- 系统配置（键值对）
CREATE TABLE system_configs (
	"key" VARCHAR(64) NOT NULL, 
	value TEXT, 
	value_type VARCHAR(16) NOT NULL, 
	"group" VARCHAR(32) NOT NULL, 
	title VARCHAR(64), 
	description VARCHAR(255), 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_system_configs_key ON system_configs ("key");

CREATE INDEX ix_system_configs_group ON system_configs ("group");

-- 用户（普通用户 / 内容审核员 / 管理员）
CREATE TABLE users (
	username VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(32) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	student_id VARCHAR(32) NOT NULL, 
	nickname VARCHAR(64), 
	avatar VARCHAR(255), 
	email VARCHAR(128), 
	phone VARCHAR(32), 
	ban_reason VARCHAR(255), 
	banned_at DATETIME, 
	banned_by INTEGER, 
	last_login_at DATETIME, 
	last_login_ip VARCHAR(64), 
	login_count INTEGER NOT NULL, 
	post_count INTEGER NOT NULL, 
	remark VARCHAR(255), 
	handover_to_id INTEGER, 
	handover_at DATETIME, 
	handover_effective_at DATETIME, 
	handover_freeze_at DATETIME, 
	handover_prev_role VARCHAR(32), 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_users_handover_to_id ON users (handover_to_id);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE UNIQUE INDEX ix_users_student_id ON users (student_id);

CREATE INDEX ix_users_status ON users (status);

CREATE INDEX ix_users_handover_freeze_at ON users (handover_freeze_at);

CREATE INDEX ix_users_role ON users (role);

CREATE INDEX ix_users_handover_effective_at ON users (handover_effective_at);

-- 管理员-模块授权（RBAC 预留，未启用）
CREATE TABLE admin_module_access (
	user_id INTEGER NOT NULL, 
	module_code VARCHAR(64) NOT NULL, 
	permission VARCHAR(32) NOT NULL, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_admin_module UNIQUE (user_id, module_code), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_admin_module_access_module_code ON admin_module_access (module_code);

CREATE INDEX ix_admin_module_access_user_id ON admin_module_access (user_id);

-- 站内私信
CREATE TABLE messages (
	sender_id INTEGER NOT NULL, 
	receiver_id INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	msg_type VARCHAR(16) NOT NULL, 
	media TEXT, 
	is_read BOOLEAN NOT NULL, 
	read_at DATETIME, 
	conversation_key VARCHAR(64), 
	post_id INTEGER, 
	sender_deleted BOOLEAN NOT NULL, 
	receiver_deleted BOOLEAN NOT NULL, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sender_id) REFERENCES users (id), 
	FOREIGN KEY(receiver_id) REFERENCES users (id)
);

CREATE INDEX ix_messages_receiver_id ON messages (receiver_id);

CREATE INDEX ix_messages_msg_type ON messages (msg_type);

CREATE INDEX ix_messages_is_read ON messages (is_read);

CREATE INDEX ix_messages_sender_id ON messages (sender_id);

CREATE INDEX ix_messages_conversation_key ON messages (conversation_key);

-- 站内通知
CREATE TABLE notifications (
	user_id INTEGER NOT NULL, 
	type VARCHAR(32) NOT NULL, 
	title VARCHAR(128) NOT NULL, 
	content TEXT, 
	is_read BOOLEAN NOT NULL, 
	read_at DATETIME, 
	link VARCHAR(255), 
	ref_id INTEGER, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_notifications_type ON notifications (type);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE INDEX ix_notifications_is_read ON notifications (is_read);

-- 帖子（所有模块统一存储，type 区分模块；含审核指派字段）
CREATE TABLE posts (
	type VARCHAR(64) NOT NULL, 
	user_id INTEGER NOT NULL, 
	title VARCHAR(128), 
	content TEXT, 
	media TEXT, 
	location VARCHAR(128), 
	happened_at DATETIME, 
	contact VARCHAR(128) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	audit_status VARCHAR(16) NOT NULL, 
	audit_remark VARCHAR(255), 
	audited_by INTEGER, 
	audited_at DATETIME, 
	assignee_id INTEGER, 
	assigned_by INTEGER, 
	assigned_at DATETIME, 
	assignment_expires_at DATETIME, 
	is_top BOOLEAN NOT NULL, 
	view_count INTEGER NOT NULL, 
	comment_count INTEGER NOT NULL, 
	favorite_count INTEGER NOT NULL, 
	like_count INTEGER NOT NULL, 
	is_deleted BOOLEAN NOT NULL, 
	deleted_at DATETIME, 
	deleted_by INTEGER, 
	ext_json TEXT, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

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

-- 上传文件记录
CREATE TABLE upload_files (
	user_id INTEGER, 
	filename VARCHAR(255) NOT NULL, 
	original_name VARCHAR(255), 
	path VARCHAR(255) NOT NULL, 
	url VARCHAR(255) NOT NULL, 
	mime VARCHAR(64), 
	media_type VARCHAR(16) NOT NULL, 
	size INTEGER NOT NULL, 
	post_id INTEGER, 
	owner_type VARCHAR(16), 
	owner_id INTEGER, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_upload_files_owner_type ON upload_files (owner_type);

CREATE INDEX ix_upload_files_owner_id ON upload_files (owner_id);

CREATE INDEX ix_upload_owner ON upload_files (owner_type, owner_id);

CREATE INDEX ix_upload_files_user_id ON upload_files (user_id);

CREATE INDEX ix_upload_files_post_id ON upload_files (post_id);

-- 帖子评论
CREATE TABLE comments (
	post_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	parent_id INTEGER, 
	root_id INTEGER, 
	content TEXT NOT NULL, 
	media TEXT, 
	reply_to_user_id INTEGER, 
	like_count INTEGER NOT NULL, 
	reply_count INTEGER NOT NULL, 
	is_deleted BOOLEAN NOT NULL, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(parent_id) REFERENCES comments (id)
);

CREATE INDEX ix_comments_post_id ON comments (post_id);

CREATE INDEX ix_comments_root_id ON comments (root_id);

CREATE INDEX ix_comments_user_id ON comments (user_id);

CREATE INDEX ix_comments_parent_id ON comments (parent_id);

CREATE INDEX ix_comments_reply_to_user_id ON comments (reply_to_user_id);

CREATE INDEX ix_comments_is_deleted ON comments (is_deleted);

-- 收藏
CREATE TABLE favorites (
	user_id INTEGER NOT NULL, 
	post_id INTEGER NOT NULL, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_favorite_user_post UNIQUE (user_id, post_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id)
);

CREATE INDEX ix_favorites_post_id ON favorites (post_id);

CREATE INDEX ix_favorites_user_id ON favorites (user_id);

-- 审核流水（指派 / 认领 / 退回 / 通过 / 拒绝）
CREATE TABLE post_audit_logs (
	post_id INTEGER NOT NULL, 
	action VARCHAR(16) NOT NULL, 
	actor_id INTEGER, 
	assignee_id INTEGER, 
	assign_source VARCHAR(16), 
	remark VARCHAR(255), 
	duration_ms INTEGER, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id)
);

CREATE INDEX ix_post_audit_logs_actor_id ON post_audit_logs (actor_id);

CREATE INDEX ix_post_audit_logs_post_id ON post_audit_logs (post_id);

CREATE INDEX ix_post_audit_logs_assignee_id ON post_audit_logs (assignee_id);

CREATE INDEX ix_post_audit_logs_post_action ON post_audit_logs (post_id, action);

-- 帖子点赞
CREATE TABLE post_likes (
	user_id INTEGER NOT NULL, 
	post_id INTEGER NOT NULL, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_post_like_user_post UNIQUE (user_id, post_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id)
);

CREATE INDEX ix_post_likes_user_id ON post_likes (user_id);

CREATE INDEX ix_post_likes_post_id ON post_likes (post_id);

-- 举报
CREATE TABLE reports (
	reporter_id INTEGER NOT NULL, 
	post_id INTEGER, 
	target_user_id INTEGER, 
	reason VARCHAR(255) NOT NULL, 
	detail TEXT, 
	status VARCHAR(16) NOT NULL, 
	handled_by INTEGER, 
	handled_at DATETIME, 
	handle_remark VARCHAR(255), 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(reporter_id) REFERENCES users (id), 
	FOREIGN KEY(post_id) REFERENCES posts (id)
);

CREATE INDEX ix_reports_reporter_id ON reports (reporter_id);

CREATE INDEX ix_reports_target_user_id ON reports (target_user_id);

CREATE INDEX ix_reports_status ON reports (status);

CREATE INDEX ix_reports_post_id ON reports (post_id);

-- 评论点赞
CREATE TABLE comment_likes (
	user_id INTEGER NOT NULL, 
	comment_id INTEGER NOT NULL, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_comment_like_user_comment UNIQUE (user_id, comment_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(comment_id) REFERENCES comments (id)
);

CREATE INDEX ix_comment_likes_comment_id ON comment_likes (comment_id);

CREATE INDEX ix_comment_likes_user_id ON comment_likes (user_id);
