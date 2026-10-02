# -*- coding: utf-8 -*-
"""开发启动入口：python run.py

生产部署建议用 WSGI 服务器：
    waitress-serve --listen=0.0.0.0:5000 run:app      # Windows
    gunicorn -w 4 -b 0.0.0.0:5000 run:app             # Linux
"""

import os

from app import create_app
from app.extensions import db

app = create_app(os.getenv('FLASK_CONFIG', 'development'))


@app.shell_context_processor
def make_shell_context():
    """flask shell 里预置常用对象。"""
    from app.models import Module, Post, SystemConfig, User

    return {'db': db, 'User': User, 'Post': Post, 'Module': Module, 'SystemConfig': SystemConfig}


if __name__ == '__main__':
    host = os.getenv('HOST', '127.0.0.1')
    port = int(os.getenv('PORT', 5000))
    # 首次运行自动建表，避免「忘了 flask db upgrade」导致报错
    with app.app_context():
        db.create_all()
    app.run(host=host, port=port, debug=app.config.get('DEBUG', True))
