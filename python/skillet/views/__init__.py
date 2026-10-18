"""Blueprint registration for all Skillet routes."""

from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from .cookbooks import bp as cookbooks_bp
    from .grocery import bp as grocery_bp
    from .importer import bp as importer_bp
    from .invites import bp as invites_bp
    from .main import bp as main_bp
    from .plans import bp as plans_bp
    from .recipes import bp as recipes_bp
    from .shop import bp as shop_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(cookbooks_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(plans_bp)
    app.register_blueprint(grocery_bp)
    app.register_blueprint(importer_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(invites_bp)
