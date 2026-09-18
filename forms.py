"""
Mini Search Engine - WTForms Authentication Forms
=================================================
Includes CSRF token protection, strict email validation, and minimum password length checks.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo


class LoginForm(FlaskForm):
    """User login form with CSRF protection and validation."""
    email = StringField(
        "Email Address",
        validators=[
            DataRequired(message="Please enter your email address."),
            Email(message="Please enter a valid email address."),
            Length(max=255),
        ],
        render_kw={"placeholder": "you@example.com", "autocomplete": "email"},
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Please enter your password."),
            Length(min=8, max=128, message="Password must be at least 8 characters."),
        ],
        render_kw={"placeholder": "••••••••", "autocomplete": "current-password"},
    )
    submit = SubmitField("Sign In")


class SignupForm(FlaskForm):
    """User registration form with password confirmation and format validation."""
    email = StringField(
        "Email Address",
        validators=[
            DataRequired(message="Please enter your email address."),
            Email(message="Please enter a valid email address."),
            Length(max=255),
        ],
        render_kw={"placeholder": "you@example.com", "autocomplete": "email"},
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Please choose a password."),
            Length(min=8, max=128, message="Password must be at least 8 characters."),
        ],
        render_kw={"placeholder": "Minimum 8 characters", "autocomplete": "new-password"},
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(message="Please confirm your password."),
            EqualTo("password", message="Passwords do not match. Please re-enter."),
        ],
        render_kw={"placeholder": "Re-type your password", "autocomplete": "new-password"},
    )
    submit = SubmitField("Create Account")
