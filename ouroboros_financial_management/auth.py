from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import User
from .money import ValidationError, normalize_username, validate_password
from .security import rate_limit
from .services import seed_user_defaults

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
@rate_limit(limit=5, window_seconds=60, label="register")
def register():
    if g.get("user"):
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        try:
            username = normalize_username(request.form.get("username"))
            password = validate_password(request.form.get("password"))
            confirm = str(request.form.get("confirm_password") or "")
            if password != confirm:
                raise ValidationError("Passwords do not match.")
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            seed_user_defaults(user)
            db.session.commit()
            flash("Account created. Log in with your new credentials.", "success")
            return redirect(url_for("auth.login"))
        except IntegrityError:
            db.session.rollback()
            flash("Username already exists.", "error")
        except ValidationError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("auth/register.html", page_title="Register")


@bp.route("/login", methods=["GET", "POST"])
@rate_limit(limit=10, window_seconds=60, label="login")
def login():
    if g.get("user"):
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        username = str(request.form.get("username") or "")[:64]
        password = str(request.form.get("password") or "")[:256]
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session.clear()
            session.permanent = True
            session["user_id"] = user.id
            flash("Logged in.", "success")
            return redirect(url_for("main.dashboard"))
        flash("Invalid credentials.", "error")
    return render_template("auth/login.html", page_title="Login")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("auth.login"))
