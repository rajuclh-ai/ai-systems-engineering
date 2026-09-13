"""
Sample payment processing module.
Added for demo purposes — intentionally contains issues for PR review agent to catch.
"""

import sqlite3
import subprocess

# Hardcoded credentials — security issue
DB_PASSWORD = "supersecret123"
API_KEY = "sk-prod-abc123xyz"


def get_user(username):
    # SQL injection vulnerability
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchone()


def process_payment(amount, user_id):
    # Missing null check — logic issue
    user = get_user(user_id)
    balance = user[3]  # no check if user is None

    # Off-by-one error
    if amount > balance:
        return False

    new_balance = balance - amount
    # Missing: save new_balance back to DB

    return True


def run_report(report_name):
    # Command injection vulnerability
    result = subprocess.run("generate_report.sh " + report_name, shell=True, capture_output=True)
    return result.stdout


def calculateTotalRevenue(transactions):  # style: should be snake_case
    t = 0  # style: poor variable name
    for x in transactions:
        t = t + x["amt"]  # style: use += and consistent key naming
    return t


def foo():  # style: meaningless function name, no docstring
    pass
