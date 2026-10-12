import os

from flask import Flask, jsonify

from . import db
from .routes import bp
from .seed import seed


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get(
            "DATABASE", os.path.join(app.instance_path, "slotdesk.sqlite")
        ),
    )
    if config:
        app.config.update(config)

    os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)
    app.teardown_appcontext(db.close_db)
    app.register_blueprint(bp, url_prefix="/api")

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "Not found."}), 404

    @app.errorhandler(405)
    def not_allowed(_e):
        return jsonify({"error": "Method not allowed."}), 405

    with app.app_context():
        db.init_db()

    @app.cli.command("seed")
    def seed_command():
        """Insert demo users and slots."""
        seed(db.get_db())
        print("Seeded. Admin: admin@slotdesk.test / admin12345  |  User: demo@slotdesk.test / demo12345")

    return app
