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

CREATE INDEX ix_login_logs_student_id ON login_logs (student_id);

CREATE INDEX ix_login_logs_user_id ON login_logs (user_id);

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

CREATE INDEX ix_operation_logs_user_id ON operation_logs (user_id);

CREATE INDEX ix_operation_logs_log_type ON operation_logs (log_type);

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

CREATE INDEX ix_system_configs_group ON system_configs ("group");

CREATE UNIQUE INDEX ix_system_configs_key ON system_configs ("key");

-- 用户（学生 / 管理员）
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
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_users_role ON users (role);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE INDEX ix_users_status ON users (status);

CREATE UNIQUE INDEX ix_users_student_id ON users (student_id);

-- 管理员-模块授权（RBAC 预留）
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
	is_read BOOLEAN NOT NULL, 
	read_at DATETIME, 
	conversation_key VARCHAR(64), 
	post_id INTEGER, 
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sender_id) REFERENCES users (id), 
	FOREIGN KEY(receiver_id) REFERENCES users (id)
);

CREATE INDEX ix_messages_sender_id ON messages (sender_id);

CREATE INDEX ix_messages_conversation_key ON messages (conversation_key);

CREATE INDEX ix_messages_is_read ON messages (is_read);

CREATE INDEX ix_messages_receiver_id ON messages (receiver_id);

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

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE INDEX ix_notifications_type ON notifications (type);

CREATE INDEX ix_notifications_is_read ON notifications (is_read);

-- 帖子（所有模块统一存储，type 区分模块）
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
	is_top BOOLEAN NOT NULL, 
	view_count INTEGER NOT NULL, 
	comment_count INTEGER NOT NULL, 
	favorite_count INTEGER NOT NULL, 
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

CREATE INDEX ix_posts_audit_status ON posts (audit_status);

CREATE INDEX ix_posts_user_id ON posts (user_id);

CREATE INDEX ix_posts_audit_created ON posts (audit_status, created_at);

CREATE INDEX ix_posts_type ON posts (type);

CREATE INDEX ix_posts_is_deleted ON posts (is_deleted);

CREATE INDEX ix_posts_status ON posts (status);

CREATE INDEX ix_posts_is_top ON posts (is_top);

CREATE INDEX ix_posts_type_status_deleted ON posts (type, status, is_deleted);

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
	id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_upload_files_user_id ON upload_files (user_id);

CREATE INDEX ix_upload_files_post_id ON upload_files (post_id);

-- 帖子评论
CREATE TABLE comments (
	post_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	parent_id INTEGER, 
	content TEXT NOT NULL, 
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

CREATE INDEX ix_comments_is_deleted ON comments (is_deleted);

CREATE INDEX ix_comments_user_id ON comments (user_id);

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

CREATE INDEX ix_reports_status ON reports (status);

CREATE INDEX ix_reports_post_id ON reports (post_id);

CREATE INDEX ix_reports_target_user_id ON reports (target_user_id);
