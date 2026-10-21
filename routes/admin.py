from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from database.db import query_all, query_one, execute
from routes.auth import login_required, roles_required
from services import audit, auth_service

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/audit")
@roles_required("admin")
def audit_log():
    prefix = request.args.get("action", "").strip()
    return render_template("admin_audit.html", events=audit.recent_events(200, prefix or None), action=prefix)


@admin_bp.route("/admin/users")
@roles_required("admin")
def users():
    return render_template("admin_users.html", users=query_all("SELECT id, username, role, created_at FROM users ORDER BY username"))


@admin_bp.route("/admin/users/add", methods=["POST"])
@roles_required("admin")
def add_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "teacher")
    if role not in ("admin", "teacher") or not username:
        flash("Username and a valid role are required.", "danger")
    elif query_one("SELECT 1 FROM users WHERE username = ?", (username,)):
        flash("That username already exists.", "danger")
    elif (err := auth_service.validate_new_password(password, username)):
        flash(err, "danger")
    else:
        execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, auth_service.hash_password(password), role))
        audit.log_event("user.create", "user", username, details={"role": role})
        flash(f"User '{username}' created.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/admin/users/<int:user_id>/reset_password", methods=["POST"])
@roles_required("admin")
def reset_password(user_id):
    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    password = request.form.get("password", "")
    if not user:
        flash("User not found.", "danger")
    elif (err := auth_service.validate_new_password(password, user["username"])):
        flash(err, "danger")
    else:
        execute("UPDATE users SET password_hash = ? WHERE id = ?", (auth_service.hash_password(password), user_id))
        execute("DELETE FROM login_attempts WHERE username = ?", (user["username"],))  # clears any lockout
        audit.log_event("user.password_reset", "user", user["username"])
        flash(f"Password reset for '{user['username']}'.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_user(user_id):
    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    admins = query_one("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")["c"]
    if not user:
        flash("User not found.", "danger")
    elif user["id"] == session.get("user_id"):
        flash("You can't delete your own account while logged in.", "danger")
    elif user["role"] == "admin" and admins <= 1:
        flash("You can't delete the last admin account.", "danger")
    else:
        execute("DELETE FROM users WHERE id = ?", (user_id,))
        audit.log_event("user.delete", "user", user["username"])
        flash(f"User '{user['username']}' deleted.", "info")
    return redirect(url_for("admin.users"))


@admin_bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        from werkzeug.security import check_password_hash
        user = query_one("SELECT * FROM users WHERE id = ?", (session["user_id"],))
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not check_password_hash(user["password_hash"], current):
            flash("Current password is incorrect.", "danger")
        elif new != confirm:
            flash("New passwords don't match.", "danger")
        elif new == current:
            flash("Choose a password different from the current one.", "danger")
        elif (err := auth_service.validate_new_password(new, user["username"])):
            flash(err, "danger")
        else:
            execute("UPDATE users SET password_hash = ? WHERE id = ?", (auth_service.hash_password(new), user["id"]))
            audit.log_event("user.password_change", "user", user["username"])
            flash("Password updated.", "success")
            return redirect(url_for("dashboard.index"))
    return render_template("account_password.html")
