from pathlib import Path
import os
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import inspect, text
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to continue.'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    if os.getenv('RENDER') and not app.config.get('SECRET_KEY'):
        raise RuntimeError('SECRET_KEY must be set in production.')
    Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app); login_manager.init_app(app); csrf.init_app(app)
    from .routes import bp
    app.register_blueprint(bp)
    @app.get('/health')
    def health():
        return {'status': 'ok'}
    @app.template_filter('fromjson')
    def fromjson_filter(value):
        import json
        return json.loads(value)
    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template('403.html'), 403
    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('404.html'), 404
    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template('500.html'), 500
    with app.app_context():
        db.create_all()

        # Lightweight compatibility migration for databases created before
        # student profile pictures were added.  create_all() does not add a
        # new column to an existing SQLite table.
        if db.engine.dialect.name == 'sqlite':
            columns = {column['name'] for column in inspect(db.engine).get_columns('user')}
            if 'profile_photo' not in columns:
                with db.engine.begin() as connection:
                    connection.execute(text('ALTER TABLE user ADD COLUMN profile_photo VARCHAR(255)'))

        # Seed only a brand-new database. After deployment, administrators
        # must be free to add, edit and remove content without startup code
        # overwriting their changes.
        from .models import Topic
        if Topic.query.count() == 0:
            from .seed import seed_database
            seed_database()
    return app
