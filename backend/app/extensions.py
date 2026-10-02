# -*- coding: utf-8 -*-
"""Flask 扩展单例。

所有扩展都在这里实例化但不绑定 app，交由 `create_app()` 中的
`init_app()` 完成绑定，避免循环导入（工厂模式的标准写法）。
"""

from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
