import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    """Show account"""
    users = db.execute("SELECT * FROM users WHERE id = ?;", session["user_id"])
    owned_cash = users[0]['cash']

    # Get user currently owned stocks
    summaries_s = db.execute("""SELECT * FROM transactions
                              WHERE sender = ? ;""", users[0]['username'])
    summaries_r = db.execute("""SELECT * FROM transactions
                              WHERE receiver = ?;""", users[0]['username'])

    # Calcuate total price for each stock
    summaries_s = [dict(x, **{'amount sent': x['amount']}) for x in summaries_s]

    summaries_r = [dict(x, **{'amount received': x['amount']}) for x in summaries_r]

    sum_totals = owned_cash + sum([x['amount received'] for x in summaries_r]) - sum([x['amount sent'] for x in summaries_s])

    return render_template("index.html", owned_cash=owned_cash, summaries=summaries_s + summaries_r, sum_totals=sum_totals,user=session["username"])


@app.route("/transactions")
@login_required
def transactions():
    """Show history of transactions"""
    transactions = db.execute("SELECT * FROM transactions WHERE sender = %s OR receiver = %s;", session["username"],session["username"])
    return render_template("transactions.html", transactions=transactions,user=session["username"])


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("MISSING USERNAME")

        if not request.form.get("password"):
            return apology("MISSING PASSWORD")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?;", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        session["username"] = rows[0]["username"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    """Get stock quote."""
    if request.method == "POST":
        # Ensure Symbol is exist
        check_user = db.execute("SELECT * FROM users WHERE username = %s;", request.form.get("username"))
        if len(check_user) < 1:
            return apology("INEXSTING USERNAME")
        return render_template("search.html", users=check_user)
    else:
        return render_template("search.html", )


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        if not (username := request.form.get("username")):
            return apology("MISSING USERNAME")

        if not (password := request.form.get("password")):
            return apology("MISSING PASSWORD")

        if not (confirmation := request.form.get("confirmation")):
            return apology("PASSWORD DON'T MATCH")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?;", username)

        # Ensure username not in database
        if len(rows) != 0:
            return apology(f"The username '{username}' already exists. Please choose another name.")

        # Ensure first password and second password are matched
        if password != confirmation:
            return apology("password not matched")

        # Insert username into database
        id = db.execute("INSERT INTO users (username, hash) VALUES (?, ?);",
                        username, generate_password_hash(password))

        # Remember which user has logged in
        session["user_id"] = id

        flash("Registered!")

        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/send", methods=["GET", "POST"])
@login_required
def send():
    """Send money"""
    receiver = db.execute("""SELECT username as receiver
                                  FROM users
                                  WHERE username = ?;""", request.form.get("receiver"))
    users = db.execute("SELECT * FROM users WHERE id = ?;", session["user_id"])

    check_user = db.execute("SELECT * FROM users WHERE username = %s;", request.form.get("receiver"))


    if request.method == "POST":
        if not (receiver := request.form.get("receiver")):
            return apology("MISSING USER")

        if len(check_user) < 1:
            return apology("INEXSTING USERNAME")
            
        if not (money := request.form.get("money")):
            return apology("MISSING AMOUNT")

        # Check share is numeric data type
        try:
            money = int(money)
        except ValueError:
            return apology("INVALID AMOUNT")

        # Check shares is positive number
        if not (money > 0):
            return apology("INVALID AMOUNT")

        if (receiver == ""):
            return apology("INVALID USER")

        if users[0]['available_cash'] < money:
            return apology("YOU WISH YOU CAN")

        # Get user currently owned cash
        rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

        # Update user owned cash
        db.execute("UPDATE users SET available_cash = ? WHERE id = ?;",
                   (rows[0]['available_cash'] - money), session["user_id"])

        # Update user owned cash
        db.execute("UPDATE users SET available_cash = ? WHERE username = ?;",
                   (rows[0]['available_cash'] + money), receiver)

        # Execute a transaction
        db.execute("INSERT INTO transactions(sender, receiver, amount) VALUES(?, ?, ?);",
                   session["username"], receiver, money)

        flash("Sent!")

        return redirect("/")

    else:
        return render_template("send.html", symbols=receiver)


@app.route("/reset", methods=["GET", "POST"])
@login_required
def reset():
    if request.method == "POST":
        if not (password := request.form.get("password")):
            return apology("MISSING OLD PASSWORD")

        rows = db.execute("SELECT * FROM users WHERE id = ?;", session["user_id"])

        if not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("INVALID PASSWORD")

        if not (new_password := request.form.get("new_password")):
            return apology("MISSING NEW PASSWORD")

        if not (confirmation := request.form.get("confirmation")):
            return apology("MISSING CONFIRMATION")

        if new_password != confirmation:
            return apology("PASSWORD NOT MATCH")

        db.execute("UPDATE users set hash = ? WHERE id = ?;",
                   generate_password_hash(new_password), session["user_id"])

        flash("Password reset successful!")

        return redirect("/")
    else:
        return render_template("reset.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)