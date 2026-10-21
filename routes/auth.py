from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from core.security import login_required, roles_required  # re-exported for the other route modules
from services import auth_service, audit

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            user = auth_service.authenticate(username, password, request.remote_addr)
        except auth_service.LockedOutError:
            audit.log_event("auth.locked_out", "user", username, username=username)
            flash("Too many failed attempts. Please wait a few minutes and try again.", "danger")
            return render_template("login.html"), 429

        if user:
            session.clear()  # new session on login (prevents session fixation)
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            audit.log_event("auth.login", "user", user["username"])
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("dashboard.index"))

        audit.log_event("auth.login_failed", "user", username, username=username)
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    if "username" in session:
        audit.log_event("auth.logout", "user", session["username"])
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
