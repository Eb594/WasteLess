import sqlite3
import re
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


app = Flask(__name__)
app.secret_key = "wasteless-development-key"

DATABASE = Path(__file__).parent / "wasteless.db"


# =====================================
# DATABASE CONNECTION
# =====================================

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# =====================================
# VENDOR LOGIN PROTECTION
# =====================================

def vendor_login_required(route_function):

    @wraps(route_function)
    def wrapper(*args, **kwargs):

        if "vendor_id" not in session:
            flash("Please log in to access your vendor account.", "error")
            return redirect(url_for("vendor_login"))

        return route_function(*args, **kwargs)

    return wrapper


# =====================================
# DATABASE INITIALIZATION
# =====================================

def initialize_database():

    connection = get_db_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS food_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            original_price REAL NOT NULL,
            discounted_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            location TEXT NOT NULL,
            collection_deadline TEXT NOT NULL,
            emoji TEXT NOT NULL
        )
    """)

    columns = connection.execute(
        "PRAGMA table_info(food_listings)"
    ).fetchall()

    column_names = [column["name"] for column in columns]

    if "vendor_id" not in column_names:
        connection.execute("""
            ALTER TABLE food_listings
            ADD COLUMN vendor_id INTEGER REFERENCES vendors(id)
        """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_id INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (food_id) REFERENCES food_listings(id)
        )
    """)

    # Temporary password-reset tokens. Only token hashes are stored.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vendor_id) REFERENCES vendors(id)
        )
    """)

    count = connection.execute(
        "SELECT COUNT(*) FROM food_listings"
    ).fetchone()[0]

    if count == 0:

        sample_foods = [
            (
                "Fresh Bakery Bread", "Bakery",
                "Freshly baked loaves available at a discount.",
                2000, 1200, 15, "Yaba, Lagos", "7:00 PM", "🥖"
            ),
            (
                "Fresh Vegetable Basket", "Fruits & Vegetables",
                "A selection of fresh seasonal vegetables.",
                5000, 3000, 8, "Ikeja, Lagos", "6:00 PM", "🥦"
            ),
            (
                "Chicken Sandwich", "Prepared Meals",
                "Ready-to-eat chicken sandwiches.",
                3500, 2100, 6, "Surulere, Lagos", "5:30 PM", "🥪"
            ),
            (
                "Fresh Fruit Pack", "Fruits & Vegetables",
                "A pack of fresh, seasonal fruit.",
                4000, 2500, 10, "Lekki, Lagos", "6:30 PM", "🍎"
            ),
            (
                "Assorted Pastries", "Bakery",
                "A selection of assorted bakery pastries.",
                3000, 1800, 12, "Victoria Island, Lagos", "7:30 PM", "🥐"
            ),
            (
                "Rice Meal Pack", "Prepared Meals",
                "A freshly prepared rice meal.",
                4500, 3000, 5, "Yaba, Lagos", "5:00 PM", "🍱"
            )
        ]

        connection.executemany("""
            INSERT INTO food_listings (
                name, category, description,
                original_price, discounted_price,
                quantity, location, collection_deadline, emoji
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_foods)

    connection.commit()
    connection.close()


# =====================================
# VENDOR REGISTRATION
# =====================================

@app.route("/vendor/register", methods=["GET", "POST"])
def vendor_register():

    if "vendor_id" in session:
        return redirect(url_for("vendor_reservations"))

    if request.method == "POST":

        business_name = request.form.get(
            "business_name", ""
        ).strip()

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not business_name or not email or not password:
            flash("Please complete all fields.", "error")
            return redirect(url_for("vendor_register"))

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Please enter a valid email address.", "error")
            return redirect(url_for("vendor_register"))

        if len(password) < 8:
            flash("Your password must contain at least 8 characters.", "error")
            return redirect(url_for("vendor_register"))

        if password != confirm_password:
            flash("Your passwords do not match.", "error")
            return redirect(url_for("vendor_register"))

        connection = get_db_connection()

        existing_vendor = connection.execute(
            "SELECT id FROM vendors WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_vendor:
            connection.close()
            flash("An account with this email already exists.", "error")
            return redirect(url_for("vendor_register"))

        hashed_password = generate_password_hash(password)

        connection.execute("""
            INSERT INTO vendors (business_name, email, password)
            VALUES (?, ?, ?)
        """, (business_name, email, hashed_password))

        connection.commit()
        connection.close()

        flash("Your vendor account has been created. Please log in.", "success")

        return redirect(url_for("vendor_login"))

    return render_template("vendor_register.html")


# =====================================
# VENDOR LOGIN
# =====================================

@app.route("/vendor/login", methods=["GET", "POST"])
def vendor_login():

    if "vendor_id" in session:
        return redirect(url_for("vendor_reservations"))

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db_connection()

        vendor = connection.execute("""
            SELECT * FROM vendors
            WHERE email = ?
        """, (email,)).fetchone()

        connection.close()

        if vendor is None or not check_password_hash(
            vendor["password"], password
        ):
            flash("Incorrect email or password.", "error")
            return redirect(url_for("vendor_login"))

        session.clear()
        session["vendor_id"] = vendor["id"]
        session["business_name"] = vendor["business_name"]

        flash("Welcome back, " + vendor["business_name"] + "!", "success")

        return redirect(url_for("vendor_reservations"))

    return render_template("vendor_login.html")


# =====================================
# VENDOR LOGOUT
# =====================================

@app.route("/vendor/logout")
@vendor_login_required
def vendor_logout():

    session.clear()

    flash("You have logged out successfully.", "success")

    return redirect(url_for("vendor_login"))


# =====================================
# FORGOT VENDOR PASSWORD
# =====================================

@app.route("/vendor/forgot-password", methods=["GET", "POST"])
def vendor_forgot_password():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Please enter your account email address.", "error")
            return redirect(url_for("vendor_forgot_password"))

        connection = get_db_connection()

        vendor = connection.execute("""
            SELECT id FROM vendors
            WHERE email = ?
        """, (email,)).fetchone()

        # Use the same response whether or not the account exists.
        flash(
            "If an account exists for that email, a reset link has been "
            "generated. During local development, check your Flask terminal.",
            "success"
        )

        if vendor:
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(
                raw_token.encode("utf-8")
            ).hexdigest()

            expires_at = (
                datetime.now(timezone.utc) + timedelta(minutes=15)
            ).isoformat()

            # Invalidate any previous unused reset links for this vendor.
            connection.execute("""
                UPDATE password_reset_tokens
                SET used_at = ?
                WHERE vendor_id = ? AND used_at IS NULL
            """, (datetime.now(timezone.utc).isoformat(), vendor["id"]))

            connection.execute("""
                INSERT INTO password_reset_tokens (
                    vendor_id, token_hash, expires_at
                )
                VALUES (?, ?, ?)
            """, (vendor["id"], token_hash, expires_at))

            connection.commit()

            reset_link = url_for(
                "vendor_reset_password",
                token=raw_token,
                _external=True
            )

            # Development only: an email service will replace this later.
            app.logger.warning(
                "LOCAL DEVELOPMENT password reset link: %s",
                reset_link
            )

        connection.close()
        return redirect(url_for("vendor_forgot_password"))

    return render_template("vendor_forgot_password.html")


# =====================================
# RESET VENDOR PASSWORD
# =====================================

@app.route("/vendor/reset-password/<token>", methods=["GET", "POST"])
def vendor_reset_password(token):

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    connection = get_db_connection()

    reset_record = connection.execute("""
        SELECT id, vendor_id
        FROM password_reset_tokens
        WHERE token_hash = ?
          AND used_at IS NULL
          AND expires_at > ?
    """, (token_hash, now)).fetchone()

    if reset_record is None:
        connection.close()
        flash(
            "This password reset link is invalid, expired, or already used. "
            "Please request a new one.",
            "error"
        )
        return redirect(url_for("vendor_forgot_password"))

    if request.method == "POST":

        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 8:
            connection.close()
            flash(
                "Your new password must contain at least 8 characters.",
                "error"
            )
            return redirect(url_for("vendor_reset_password", token=token))

        if password != confirm_password:
            connection.close()
            flash("Your passwords do not match.", "error")
            return redirect(url_for("vendor_reset_password", token=token))

        hashed_password = generate_password_hash(password)
        used_at = datetime.now(timezone.utc).isoformat()

        try:
            connection.execute("BEGIN IMMEDIATE")

            # Recheck inside the transaction so a token cannot be reused.
            current_token = connection.execute("""
                SELECT id, vendor_id
                FROM password_reset_tokens
                WHERE token_hash = ?
                  AND used_at IS NULL
                  AND expires_at > ?
            """, (token_hash, used_at)).fetchone()

            if current_token is None:
                connection.rollback()
                connection.close()
                flash(
                    "This password reset link is invalid, expired, or already used.",
                    "error"
                )
                return redirect(url_for("vendor_forgot_password"))

            connection.execute("""
                UPDATE vendors
                SET password = ?
                WHERE id = ?
            """, (hashed_password, current_token["vendor_id"]))

            connection.execute("""
                UPDATE password_reset_tokens
                SET used_at = ?
                WHERE id = ?
            """, (used_at, current_token["id"]))

            # Invalidate any other outstanding links for this vendor.
            connection.execute("""
                UPDATE password_reset_tokens
                SET used_at = ?
                WHERE vendor_id = ?
                  AND used_at IS NULL
            """, (used_at, current_token["vendor_id"]))

            connection.commit()

        except sqlite3.Error:
            connection.rollback()
            connection.close()
            flash(
                "Something went wrong. Please request a new reset link.",
                "error"
            )
            return redirect(url_for("vendor_forgot_password"))

        connection.close()
        flash("Your password has been reset. You can now log in.", "success")
        return redirect(url_for("vendor_login"))

    connection.close()
    return render_template("vendor_reset_password.html", token=token)


# =====================================
# HOMEPAGE
# =====================================

@app.route("/")
def home():
    return render_template("index.html")


# =====================================
# MARKETPLACE
# =====================================

@app.route("/marketplace")
def marketplace():

    search_query = request.args.get("search", "").strip()
    selected_category = request.args.get("category", "").strip()
    selected_location = request.args.get("location", "").strip()

    connection = get_db_connection()

    food_listings = connection.execute("""
        SELECT * FROM food_listings
        WHERE quantity > 0
        ORDER BY id DESC
    """).fetchall()

    categories = connection.execute("""
        SELECT DISTINCT category
        FROM food_listings
        ORDER BY category
    """).fetchall()

    locations = connection.execute("""
        SELECT DISTINCT location
        FROM food_listings
        ORDER BY location
    """).fetchall()

    connection.close()

    filtered_listings = []

    for food in food_listings:

        matches_search = (
            search_query.lower() in food["name"].lower()
            or search_query.lower() in food["description"].lower()
            or search_query.lower() in food["location"].lower()
        )

        matches_category = (
            not selected_category
            or food["category"] == selected_category
        )

        matches_location = (
            not selected_location
            or food["location"] == selected_location
        )

        if matches_search and matches_category and matches_location:

            food_copy = dict(food)

            food_copy["discount_percentage"] = round(
                (
                    food["original_price"] - food["discounted_price"]
                ) / food["original_price"] * 100
            )

            filtered_listings.append(food_copy)

    return render_template(
        "marketplace.html",
        food_listings=filtered_listings,
        categories=[row["category"] for row in categories],
        locations=[row["location"] for row in locations],
        search_query=search_query,
        selected_category=selected_category,
        selected_location=selected_location
    )


# =====================================
# ADD FOOD LISTING
# =====================================

@app.route("/add-food", methods=["GET", "POST"])
@vendor_login_required
def add_food():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        location = request.form.get("location", "").strip()

        collection_deadline = request.form.get(
            "collection_deadline", ""
        ).strip()

        try:

            original_price = float(request.form.get("original_price", ""))
            discounted_price = float(
                request.form.get("discounted_price", "")
            )
            quantity = int(request.form.get("quantity", ""))

            if not all([
                name, category, description,
                location, collection_deadline
            ]):
                raise ValueError("Please complete all fields.")

            if original_price <= 0 or discounted_price <= 0:
                raise ValueError("Prices must be greater than zero.")

            if discounted_price >= original_price:
                raise ValueError(
                    "The discounted price must be lower than the original price."
                )

            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")

        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("add_food"))

        food_emojis = {
            "Bakery": "🥖",
            "Fruits & Vegetables": "🥦",
            "Prepared Meals": "🍱",
            "Dairy": "🥛",
            "Snacks": "🍪",
            "Other": "🍽️"
        }

        emoji = food_emojis.get(category, "🍽️")

        connection = get_db_connection()

        connection.execute("""
            INSERT INTO food_listings (
                name, category, description,
                original_price, discounted_price,
                quantity, location, collection_deadline,
                emoji, vendor_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, category, description,
            original_price, discounted_price,
            quantity, location, collection_deadline,
            emoji, session["vendor_id"]
        ))

        connection.commit()
        connection.close()

        flash("Your food listing has been added successfully!", "success")

        return redirect(url_for("marketplace"))

    return render_template("add_food.html")


# =====================================
# CUSTOMER RESERVATION
# =====================================

@app.route("/reserve/<int:food_id>", methods=["GET", "POST"])
def reserve_food(food_id):

    connection = get_db_connection()

    food = connection.execute("""
        SELECT * FROM food_listings
        WHERE id = ?
    """, (food_id,)).fetchone()

    if food is None:
        connection.close()
        flash("The food listing could not be found.", "error")
        return redirect(url_for("marketplace"))

    if request.method == "POST":

        customer_name = request.form.get("customer_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        quantity_text = request.form.get("quantity", "").strip()

        if not customer_name or not phone_number or not quantity_text:
            connection.close()
            flash("Please complete all reservation fields.", "error")
            return redirect(url_for("reserve_food", food_id=food_id))

        phone_digits = re.sub(r"[\s+\-()]", "", phone_number)

        if not phone_digits.isdigit() or not 7 <= len(phone_digits) <= 15:
            connection.close()
            flash("Please enter a valid phone number.", "error")
            return redirect(url_for("reserve_food", food_id=food_id))

        try:
            quantity = int(quantity_text)

            if quantity <= 0:
                raise ValueError

        except ValueError:
            connection.close()
            flash("Please enter a valid quantity greater than zero.", "error")
            return redirect(url_for("reserve_food", food_id=food_id))

        try:

            connection.execute("BEGIN IMMEDIATE")

            current_food = connection.execute("""
                SELECT quantity, discounted_price
                FROM food_listings
                WHERE id = ?
            """, (food_id,)).fetchone()

            if current_food is None or current_food["quantity"] < quantity:

                connection.rollback()
                connection.close()

                flash(
                    "Sorry, there is not enough food available for that quantity.",
                    "error"
                )

                return redirect(url_for("reserve_food", food_id=food_id))

            total_price = quantity * current_food["discounted_price"]

            connection.execute("""
                UPDATE food_listings
                SET quantity = quantity - ?
                WHERE id = ?
            """, (quantity, food_id))

            connection.execute("""
                INSERT INTO reservations (
                    food_id, customer_name, phone_number,
                    quantity, total_price
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                food_id, customer_name, phone_number,
                quantity, total_price
            ))

            reservation_id = connection.execute(
                "SELECT last_insert_rowid()"
            ).fetchone()[0]

            connection.commit()

        except sqlite3.Error:

            connection.rollback()
            connection.close()

            flash("Something went wrong. Please try again.", "error")

            return redirect(url_for("reserve_food", food_id=food_id))

        connection.close()

        return redirect(
            url_for(
                "reservation_confirmation",
                reservation_id=reservation_id
            )
        )

    connection.close()

    return render_template("reserve.html", food=food)


# =====================================
# RESERVATION CONFIRMATION
# =====================================

@app.route("/reservation/<int:reservation_id>")
def reservation_confirmation(reservation_id):

    connection = get_db_connection()

    reservation = connection.execute("""
        SELECT
            reservations.*,
            food_listings.name AS food_name,
            food_listings.location,
            food_listings.collection_deadline
        FROM reservations
        JOIN food_listings
            ON reservations.food_id = food_listings.id
        WHERE reservations.id = ?
    """, (reservation_id,)).fetchone()

    connection.close()

    if reservation is None:
        flash("Reservation not found.", "error")
        return redirect(url_for("marketplace"))

    return render_template(
        "reservation_confirmation.html",
        reservation=reservation
    )


# =====================================
# CHANGE VENDOR PASSWORD
# =====================================

@app.route("/vendor/change-password", methods=["GET", "POST"])
@vendor_login_required
def change_vendor_password():

    if request.method == "POST":

        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        connection = get_db_connection()

        vendor = connection.execute("""
            SELECT password
            FROM vendors
            WHERE id = ?
        """, (session["vendor_id"],)).fetchone()

        if vendor is None:
            connection.close()
            session.clear()
            flash("Your account could not be found. Please log in again.", "error")
            return redirect(url_for("vendor_login"))

        if not check_password_hash(vendor["password"], current_password):
            connection.close()
            flash("Your current password is incorrect.", "error")
            return redirect(url_for("change_vendor_password"))

        if len(new_password) < 8:
            connection.close()
            flash("Your new password must contain at least 8 characters.", "error")
            return redirect(url_for("change_vendor_password"))

        if new_password != confirm_password:
            connection.close()
            flash("Your new passwords do not match.", "error")
            return redirect(url_for("change_vendor_password"))

        if current_password == new_password:
            connection.close()
            flash("Your new password must be different from your current password.", "error")
            return redirect(url_for("change_vendor_password"))

        hashed_password = generate_password_hash(new_password)
        changed_at = datetime.now(timezone.utc).isoformat()

        try:
            connection.execute("BEGIN IMMEDIATE")

            connection.execute("""
                UPDATE vendors
                SET password = ?
                WHERE id = ?
            """, (hashed_password, session["vendor_id"]))

            # Invalidate any unused password-reset links for this vendor.
            connection.execute("""
                UPDATE password_reset_tokens
                SET used_at = ?
                WHERE vendor_id = ?
                  AND used_at IS NULL
            """, (changed_at, session["vendor_id"]))

            connection.commit()

        except sqlite3.Error:
            connection.rollback()
            connection.close()
            flash("Unable to update your password. Please try again.", "error")
            return redirect(url_for("change_vendor_password"))

        connection.close()
        flash("Your password has been changed successfully!", "success")
        return redirect(url_for("vendor_reservations"))

    return render_template("vendor_change_password.html")


# =====================================
# VENDOR FOOD LISTINGS
# =====================================

@app.route("/vendor/listings")
@vendor_login_required
def vendor_listings():

    connection = get_db_connection()

    listings = connection.execute("""
        SELECT *
        FROM food_listings
        WHERE vendor_id = ?
        ORDER BY id DESC
    """, (session["vendor_id"],)).fetchall()

    connection.close()

    return render_template(
        "vendor_listings.html",
        listings=listings
    )


# =====================================
# VENDOR RESERVATIONS DASHBOARD
# =====================================

@app.route("/vendor/reservations")
@vendor_login_required
def vendor_reservations():

    connection = get_db_connection()

    reservations = connection.execute("""
        SELECT
            reservations.id,
            reservations.customer_name,
            reservations.phone_number,
            reservations.quantity,
            reservations.total_price,
            reservations.status,
            food_listings.name AS food_name
        FROM reservations
        JOIN food_listings
            ON reservations.food_id = food_listings.id
        WHERE food_listings.vendor_id = ?
        ORDER BY reservations.created_at DESC
    """, (session["vendor_id"],)).fetchall()

    connection.close()

    return render_template(
        "vendor_reservations.html",
        reservations=reservations
    )


# =====================================
# UPDATE RESERVATION STATUS
# =====================================

@app.route(
    "/vendor/reservations/<int:reservation_id>/update",
    methods=["POST"]
)
@vendor_login_required
def update_reservation(reservation_id):

    allowed_statuses = ["Pending", "Confirmed", "Collected"]

    new_status = request.form.get("status", "").strip()

    if new_status not in allowed_statuses:
        flash("Invalid reservation status.", "error")
        return redirect(url_for("vendor_reservations"))

    connection = get_db_connection()

    reservation = connection.execute("""
        SELECT reservations.id
        FROM reservations
        JOIN food_listings
            ON reservations.food_id = food_listings.id
        WHERE reservations.id = ?
        AND food_listings.vendor_id = ?
    """, (reservation_id, session["vendor_id"])).fetchone()

    if reservation is None:
        connection.close()
        flash("Reservation not found.", "error")
        return redirect(url_for("vendor_reservations"))

    connection.execute("""
        UPDATE reservations
        SET status = ?
        WHERE id = ?
    """, (new_status, reservation_id))

    connection.commit()
    connection.close()

    flash("Reservation status updated successfully!", "success")

    return redirect(url_for("vendor_reservations"))


# =====================================
# RUN APPLICATION
# =====================================

if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)