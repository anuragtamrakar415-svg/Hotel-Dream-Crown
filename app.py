from flask import Flask, render_template, request, redirect, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import requests

app = Flask(__name__)

# -----------------------
# CONFIG
# -----------------------
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hotel.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "dreamcrown_secret_2026"

db = SQLAlchemy(app)


# -----------------------
# DATABASE MODELS
# -----------------------
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    date = db.Column(db.String(50))
    checkout_date = db.Column(db.String(50))
    guests = db.Column(db.String(10))
    room_id = db.Column(db.Integer)
    room_type = db.Column(db.String(100))
    amount = db.Column(db.Integer)
    advance_paid = db.Column(db.Integer)
    payment_status = db.Column(db.String(20), default="Pending")
    payment_option = db.Column(db.String(20))
    utr = db.Column(db.String(100))
    hold_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    password = db.Column(db.String(100))


class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(10))
    room_type = db.Column(db.String(50))
    price = db.Column(db.Integer)
    status = db.Column(db.String(20), default="available")


# -----------------------
# ROOMS DATA FOR USER PORTAL
# -----------------------
rooms_data = [
    {
        "id": 101,
        "name": "Family Non-AC Room",
        "desc": "Spacious room for families with two queen beds",
        "price": 599,
        "image": "https://images.unsplash.com/photo-1560185893-a55cbc8c57e8?w=600&h=400&fit=crop",
        "features": ["WiFi", "TV", "Fan", "Family Size"],
        "category": "non-ac",
        "room_number": "101"
    },
    {
        "id": 201,
        "name": "Standard Non-AC Room",
        "desc": "Comfortable budget room with fan and large windows",
        "price": 599,
        "image": "https://images.unsplash.com/photo-1618773928121-c32242e63f39?w=600&h=400&fit=crop",
        "features": ["WiFi", "TV", "Fan"],
        "category": "non-ac",
        "room_number": "201"
    },
    {
        "id": 202,
        "name": "Economy Non-AC Room",
        "desc": "Best value budget room with twin beds",
        "price": 599,
        "image": "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=600&h=400&fit=crop",
        "features": ["WiFi", "Fan", "Twin Beds"],
        "category": "non-ac",
        "room_number": "202"
    },
    {
        "id": 203,
        "name": "AC Deluxe Room",
        "desc": "Spacious AC room with king-size bed",
        "price": 899,
        "image": "https://images.unsplash.com/photo-1566665797739-1674de7a421a?w=600&h=400&fit=crop",
        "features": ["Air Conditioning", "WiFi", "TV"],
        "category": "ac",
        "room_number": "203"
    },
    {
        "id": 301,
        "name": "AC Executive Suite",
        "desc": "Luxury AC suite with balcony and work desk",
        "price": 899,
        "image": "https://images.unsplash.com/photo-1591088398332-8a7791972843?w=600&h=400&fit=crop",
        "features": ["Air Conditioning", "WiFi", "TV"],
        "category": "ac",
        "room_number": "301"
    },
    {
        "id": 302,
        "name": "AC Presidential Suite",
        "desc": "Ultimate luxury AC experience with premium amenities",
        "price": 899,
        "image": "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?w=600&h=400&fit=crop",
        "features": ["Air Conditioning", "WiFi", "TV"],
        "category": "ac",
        "room_number": "302"
    },
]


# -----------------------
# HELPER FUNCTIONS
# -----------------------
def get_room(room_id):
    for r in rooms_data:
        if r["id"] == int(room_id):
            return r
    return None


def get_room_by_number(room_number):
    for r in rooms_data:
        if r["room_number"] == str(room_number):
            return r
    return None


def clear_expired_holds():
    expire_time = datetime.utcnow() - timedelta(minutes=5)
    expired = Booking.query.filter(
        Booking.payment_status == "Pending",
        Booking.created_at < expire_time
    ).all()
    for b in expired:
        b.payment_status = "Rejected"
    db.session.commit()


def get_booked_rooms(selected_date_str):
    """Get list of room IDs that are booked for selected date"""
    try:
        selected = datetime.strptime(selected_date_str, "%Y-%m-%d")
    except Exception:
        return []

    bookings = Booking.query.filter(
        Booking.payment_status.in_(["Confirmed", "Pending", "Pending Verification"])
    ).all()

    booked = []
    for b in bookings:
        if not b.date or not b.checkout_date:
            continue
        try:
            checkin = datetime.strptime(b.date, "%Y-%m-%d")
            checkout = datetime.strptime(b.checkout_date, "%Y-%m-%d")
            if checkin <= selected < checkout:
                booked.append(b.room_id)
        except Exception:
            continue
    return booked


def get_all_booked_room_ids():
    """Get all room IDs that have any active booking (Confirmed, Pending, Pending Verification)"""
    bookings = Booking.query.filter(
        Booking.payment_status.in_(["Confirmed", "Pending", "Pending Verification"])
    ).all()
    
    booked_room_ids = []
    for b in bookings:
        if b.room_id not in booked_room_ids:
            booked_room_ids.append(b.room_id)
    
    # Also check Room table for offline booked rooms
    offline_booked_rooms = Room.query.filter_by(status="offline_booked").all()
    for room in offline_booked_rooms:
        room_data = get_room_by_number(room.room_number)
        if room_data and room_data["id"] not in booked_room_ids:
            booked_room_ids.append(room_data["id"])
    
    return booked_room_ids


def sync_user_rooms():
    """Sync room status from Room table to rooms_data for user display"""
    all_db_rooms = Room.query.all()
    for db_room in all_db_rooms:
        for room_data in rooms_data:
            if room_data["room_number"] == db_room.room_number:
                if db_room.status == "offline_booked":
                    room_data["offline_booked"] = True
                else:
                    room_data["offline_booked"] = False
                break


# =======================
# PUBLIC ROUTES
# =======================
@app.route("/")
def home():
    clear_expired_holds()
    sync_user_rooms()
    today = date.today().isoformat()
    booked_rooms = get_booked_rooms(today)
    all_booked = get_all_booked_room_ids()
    
    return render_template("index.html", rooms=rooms_data, booked_rooms=all_booked)


@app.route("/rooms")
def rooms():
    clear_expired_holds()
    sync_user_rooms()
    selected_date = request.args.get("date", date.today().isoformat())
    booked_rooms = get_booked_rooms(selected_date)
    all_booked = get_all_booked_room_ids()
    
    return render_template(
        "rooms.html",
        rooms=rooms_data,
        booked_rooms=all_booked,
        selected_date=selected_date
    )


@app.route("/dining")
def dining():
    return render_template("dining.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


# =======================
# BOOKING FLOW
# =======================
@app.route("/book/<int:room_id>", methods=["GET", "POST"])
def book(room_id):
    room = get_room(room_id)
    if not room:
        return "Room not found", 404

    error = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        checkin = request.form.get("date", "")
        checkout = request.form.get("checkout_date", "")
        guests = request.form.get("guests", "1")
        payment_option = request.form.get("payment_option", "full")

        if not checkin or not checkout:
            error = "Please select both check-in and check-out dates."
        elif checkin >= checkout:
            error = "Check-out date must be after check-in date."
        else:
            try:
                sel_checkin = datetime.strptime(checkin, "%Y-%m-%d")
                sel_checkout = datetime.strptime(checkout, "%Y-%m-%d")
                nights = (sel_checkout - sel_checkin).days
            except Exception:
                error = "Invalid date format."

            if not error:
                existing = Booking.query.filter(
                    Booking.room_id == room_id,
                    Booking.payment_status.in_(["Confirmed", "Pending", "Pending Verification"])
                ).all()

                for b in existing:
                    if not b.date or not b.checkout_date:
                        continue
                    try:
                        b_checkin = datetime.strptime(b.date, "%Y-%m-%d")
                        b_checkout = datetime.strptime(b.checkout_date, "%Y-%m-%d")
                        if sel_checkin < b_checkout and sel_checkout > b_checkin:
                            error = "This room is already booked for the selected dates."
                            break
                    except Exception:
                        continue

        if not error:
            room_price = room["price"]
            total = room_price * nights

            if payment_option == "advance":
                pay_now = max(1, round(total * 0.25))
            else:
                pay_now = total

            hold_time = datetime.utcnow() + timedelta(minutes=5)
            hold_booking = Booking(
                name=name, email=email, phone=phone,
                date=checkin, checkout_date=checkout,
                guests=guests, room_id=room_id,
                room_type=room["name"], amount=total,
                advance_paid=pay_now, payment_status="Pending",
                payment_option=payment_option, utr="",
                hold_until=hold_time, created_at=datetime.utcnow()
            )
            db.session.add(hold_booking)
            db.session.commit()

            return redirect(
                f"/payment?amount={pay_now}&total={total}&room_id={room_id}"
                f"&booking_id={hold_booking.id}&name={name}&email={email}"
                f"&phone={phone}&date={checkin}&checkout_date={checkout}"
                f"&guests={guests}&payment_option={payment_option}&nights={nights}"
            )

    return render_template("book.html", room=room, error=error)


@app.route("/payment")
def payment():
    amount = request.args.get("amount", "0")
    total = request.args.get("total", "0")
    room_id = request.args.get("room_id")
    booking_id = request.args.get("booking_id")
    name = request.args.get("name")
    email = request.args.get("email")
    phone = request.args.get("phone")
    checkin = request.args.get("date")
    checkout = request.args.get("checkout_date")
    guests = request.args.get("guests")
    payment_option = request.args.get("payment_option")
    nights = request.args.get("nights", "1")

    room = get_room(room_id)
    room_name = room["name"] if room else "Deluxe Room"

    try:
        remaining = int(total) - int(amount)
    except:
        remaining = 0

    return render_template(
        "payment.html", amount=amount, total=total, remaining=remaining,
        room_id=room_id, booking_id=booking_id, room_name=room_name,
        name=name, email=email, phone=phone, date=checkin,
        checkout_date=checkout, guests=guests, payment_option=payment_option,
        nights=nights
    )


@app.route("/confirm_payment", methods=["POST"])
def confirm_payment():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    checkin = request.form.get("date", "")
    checkout = request.form.get("checkout_date", "")
    guests = request.form.get("guests", "1")
    room_id = request.form.get("room_id")
    amount = request.form.get("amount", "0")
    total = request.form.get("total", "0")
    payment_option = request.form.get("payment_option", "full")
    utr = request.form.get("utr", "").strip()
    booking_id_str = request.form.get("booking_id", "")

    if not (len(utr) == 12 and utr.isdigit()):
        return render_template("payment.html", amount=amount, total=total, error="Invalid UTR.")

    existing_utr = Booking.query.filter_by(utr=utr).first()
    if existing_utr:
        return render_template("payment.html", amount=amount, total=total, error="UTR already used.")

    current_booking = None
    try:
        if booking_id_str:
            current_booking = Booking.query.get(int(booking_id_str))
            if current_booking:
                current_booking.utr = utr
                current_booking.phone = phone
                current_booking.payment_status = "Pending Verification"
                db.session.commit()

        # Update room status to online booked in Room table
        room = get_room(room_id)
        if room:
            db_room = Room.query.filter_by(room_number=room["room_number"]).first()
            if db_room:
                db_room.status = "online_booked"
                db.session.commit()

        if not current_booking:
            room_obj = get_room(room_id)
            current_booking = Booking(
                name=name, email=email, phone=phone,
                date=checkin, checkout_date=checkout,
                guests=guests, room_id=int(room_id),
                room_type=room_obj["name"] if room_obj else "Room",
                amount=int(total), advance_paid=int(amount),
                payment_status="Pending Verification",
                payment_option=payment_option, utr=utr,
                created_at=datetime.utcnow()
            )
            db.session.add(current_booking)
            db.session.commit()

        # Telegram Notification
        bot_token = "8673554110:AAFbqRa4Cf5gybp23LEbqCpFtLvgej1PDV8"
        chat_id = "8097209878"
        msg = (
            f"🔔 *New Booking Request!*\n"
            f"👤 Guest: {current_booking.name}\n"
            f"📞 Phone: {current_booking.phone}\n"
            f"💰 Amount: ₹{current_booking.advance_paid}\n"
            f"🔢 UTR: `{current_booking.utr}`\n"
            f"🏨 Room: {current_booking.room_type}\n"
        )
        telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(telegram_url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

        return redirect(f"/confirm/{current_booking.id}")

    except Exception as e:
        print(f"Error: {e}")
        return "Something went wrong", 500


@app.route("/confirm/<int:booking_id>")
def confirm(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    room = get_room(booking.room_id)
    remaining = (booking.amount or 0) - (booking.advance_paid or 0)
    return render_template("confirm.html", booking=booking, room=room, remaining=remaining)


@app.route("/booking-status/<int:booking_id>")
def booking_status(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return jsonify({"status": booking.payment_status})


# =======================
# ADMIN ROUTES
# =======================
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username, password=password).first()
        if admin:
            session["admin"] = True
            return redirect("/admin")
        else:
            error = "Invalid username or password."
    return render_template("admin_login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect("/admin-login")


@app.route("/change-password", methods=["GET", "POST"])
def change_password():
    if not session.get("admin"):
        return redirect("/admin-login")
    msg = None
    if request.method == "POST":
        new_password = request.form.get("password", "").strip()
        if new_password:
            admin = Admin.query.first()
            admin.password = new_password
            db.session.commit()
            msg = "Password updated successfully!"
    return render_template("change_password.html", msg=msg)


@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin-login")

    bookings = Booking.query.order_by(Booking.id.desc()).all()
    current_date = date.today().isoformat()

    total_bookings = len(bookings)
    confirmed_bookings = sum(1 for b in bookings if b.payment_status == "Confirmed")
    pending_bookings = sum(1 for b in bookings if b.payment_status == "Pending")
    total_revenue = sum((b.advance_paid or 0) for b in bookings if b.payment_status == "Confirmed")
    pending_revenue = sum((b.advance_paid or 0) for b in bookings if b.payment_status == "Pending")

    return render_template(
        "admin.html",
        bookings=bookings,
        current_date=current_date,
        total_bookings=total_bookings,
        confirmed_bookings=confirmed_bookings,
        pending_bookings=pending_bookings,
        total_revenue=total_revenue,
        pending_revenue=pending_revenue
    )


@app.route("/pending_count")
def pending_count():
    count = Booking.query.filter_by(payment_status="Pending Verification").count()
    return {"count": count}


@app.route("/admin_bookings")
def admin_bookings():
    if "admin" not in session:
        return redirect("/admin-login")

    bookings = Booking.query.order_by(Booking.id.desc()).all()

    booking_list = []
    for b in bookings:
        booking_list.append({
            "id": b.id, "name": b.name, "email": b.email, "phone": b.phone,
            "date": str(b.date), "checkout_date": str(b.checkout_date) if b.checkout_date else None,
            "guests": b.guests, "room_type": b.room_type,
            "amount": b.amount, "advance_paid": b.advance_paid,
            "payment_status": b.payment_status
        })

    current_date = date.today().isoformat()
    return render_template("admin_bookings.html", bookings=booking_list, current_date=current_date)


@app.route("/admin_rooms")
def admin_rooms():
    if not session.get("admin"):
        return redirect("/admin-login")

    rooms = Room.query.all()
    room_list = []
    for r in rooms:
        room_list.append({
            "id": r.id, "room_number": r.room_number, "room_type": r.room_type,
            "price": r.price, "status": r.status
        })

    return render_template("admin_rooms.html", rooms=room_list)


@app.route("/offline_book/<int:room_id>")
def offline_book(room_id):
    if not session.get("admin"):
        return redirect("/admin-login")

    room = Room.query.filter_by(id=room_id).first()

    if room and room.status == "available":
        room.status = "offline_booked"

        booking = Booking(
            name="Offline Guest", email="offline@hotel.com", phone="0000000000",
            date=date.today().isoformat(),
            checkout_date=(date.today() + timedelta(days=1)).isoformat(),
            guests="1", room_id=room_id, room_type=room.room_type,
            amount=room.price, advance_paid=room.price,
            payment_status="Confirmed", payment_option="offline", utr="offline"
        )
        db.session.add(booking)
        db.session.commit()

    return redirect("/admin_rooms")


@app.route("/make_room_available/<int:room_id>", methods=["POST"])
def make_room_available(room_id):
    if "admin" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        room = Room.query.filter_by(id=room_id).first()
        if room:
            room.status = "available"
            
            # Cancel any confirmed booking for this room
            booking = Booking.query.filter_by(room_id=room_id, payment_status="Confirmed").first()
            if booking:
                booking.payment_status = "Cancelled"
            
            db.session.commit()
            return jsonify({"success": True})
        return jsonify({"error": "Room not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/bulk_make_available", methods=["POST"])
def bulk_make_available():
    if "admin" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    room_ids = data.get("room_ids", [])

    try:
        for room_id in room_ids:
            room = Room.query.filter_by(id=room_id).first()
            if room:
                room.status = "available"
                booking = Booking.query.filter_by(room_id=room_id, payment_status="Confirmed").first()
                if booking:
                    booking.payment_status = "Cancelled"
        db.session.commit()
        return jsonify({"success": True, "message": f"{len(room_ids)} rooms updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/bulk_delete_rooms", methods=["POST"])
def bulk_delete_rooms():
    if "admin" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    room_ids = data.get("room_ids", [])

    try:
        for room_id in room_ids:
            room = Room.query.filter_by(id=room_id).first()
            if room:
                db.session.delete(room)
        db.session.commit()
        return jsonify({"success": True, "message": f"{len(room_ids)} rooms deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/room-bookings/<int:room_id>")
def api_room_bookings(room_id):
    if "admin" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    booking = Booking.query.filter_by(room_id=room_id, payment_status="Confirmed").first()
    if booking:
        return jsonify({
            "booking": {
                "name": booking.name, "phone": booking.phone, "email": booking.email,
                "date": booking.date, "checkout_date": booking.checkout_date,
                "guests": booking.guests, "advance_paid": booking.advance_paid,
                "payment_status": booking.payment_status
            }
        })
    return jsonify({"booking": None})


@app.route("/verify/<int:booking_id>")
def verify(booking_id):
    if not session.get("admin"):
        return redirect("/admin-login")
    booking = Booking.query.get_or_404(booking_id)
    booking.payment_status = "Confirmed"
    db.session.commit()
    return redirect("/admin")


@app.route("/reject/<int:booking_id>")
def reject(booking_id):
    if not session.get("admin"):
        return redirect("/admin-login")
    booking = Booking.query.get_or_404(booking_id)
    booking.payment_status = "Rejected"
    db.session.commit()
    return redirect("/admin")


@app.route("/delete/<int:booking_id>")
def delete(booking_id):
    if not session.get("admin"):
        return redirect("/admin-login")
    booking = Booking.query.get_or_404(booking_id)
    db.session.delete(booking)
    db.session.commit()
    return redirect("/admin")


@app.route("/check")
def check():
    bookings = Booking.query.all()
    result = ""
    for b in bookings:
        result += f"ID:{b.id} | {b.name} | Room:{b.room_id} | Status:{b.payment_status}<br>"
    return result if result else "No bookings yet."


# =======================
# RUN
# =======================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        if not Admin.query.first():
            admin = Admin(username="admin", password="1234")
            db.session.add(admin)

        if not Room.query.first():
            rooms = [
                Room(room_number="101", room_type="Family Non AC", price=599, status="available"),
                Room(room_number="201", room_type="Standard Non AC", price=599, status="available"),
                Room(room_number="202", room_type="Economy Non AC", price=599, status="available"),
                Room(room_number="203", room_type="AC Deluxe", price=899, status="available"),
                Room(room_number="301", room_type="AC Executive Suite", price=899, status="available"),
                Room(room_number="302", room_type="AC Presidential Suite", price=899, status="available")
            ]
            db.session.add_all(rooms)

        db.session.commit()
        print("✅ Database initialized!")
        print("📌 Admin Login: username='admin', password='1234'")

    app.run(debug=False)
