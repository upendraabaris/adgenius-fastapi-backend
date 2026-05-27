import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging

logger = logging.getLogger(__name__)

def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    smtp_server = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5176")

    if not smtp_username or not smtp_password:
        logger.warning(f"SMTP credentials missing. Would have sent reset email to: {to_email}")
        return False

    reset_link = f"{frontend_url}/reset-password?token={reset_token}"
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = "Password Reset Request - Growcommerce"

    body = f"""
    <html>
    <body>
        <p>Hello,</p>
        <p>We received a request to reset your password for your Growcommerce account.</p>
        <p>Click the link below to reset your password. This link will expire in 15 minutes.</p>
        <p><a href="{reset_link}" style="display:inline-block;padding:10px 20px;background-color:#007BFF;color:#ffffff;text-decoration:none;border-radius:5px;">Reset Password</a></p>
        <p>If you didn't request a password reset, you can safely ignore this email.</p>
        <p>Thanks,<br>The Growcommerce Team</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(body, 'html'))

    try:
        if smtp_port == 465:
            # SSL
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
        else:
            # TLS
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
        logger.info(f"Password reset email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
        return False

def send_verification_email(to_email: str, token: str) -> bool:
    smtp_server = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5176")

    if not smtp_username or not smtp_password:
        logger.warning(f"SMTP credentials missing. Would have sent verification email to: {to_email}")
        return False

    verify_link = f"{frontend_url}/verify-email?token={token}"
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = "Verify your email - Growcommerce"

    body = f"""
    <html>
    <body>
        <p>Hello,</p>
        <p>Welcome to Growcommerce! Please verify your email address to complete your registration.</p>
        <p>Click the link below to verify your email. This link will expire in 24 hours.</p>
        <p><a href="{verify_link}" style="display:inline-block;padding:10px 20px;background-color:#007BFF;color:#ffffff;text-decoration:none;border-radius:5px;">Verify Email</a></p>
        <p>If you didn't create an account, you can safely ignore this email.</p>
        <p>Thanks,<br>The Growcommerce Team</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(body, 'html'))

    try:
        if smtp_port == 465:
            # SSL
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
        else:
            # TLS
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
        logger.info(f"Verification email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {to_email}: {str(e)}")
        return False

def send_otp_email(to_email: str, otp: str) -> bool:
    smtp_server = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM")

    if not smtp_username or not smtp_password:
        logger.warning(f"SMTP credentials missing. Would have sent OTP email to: {to_email}")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = f"Your OTP Verification Code: {otp} - Growcommerce"

    body = f"""
    <html>
    <body>
        <p>Hello,</p>
        <p>Welcome to Growcommerce! Please verify your email address to complete your registration.</p>
        <p>Your OTP verification code is:</p>
        <h2 style="background: #f4f4f4; padding: 10px; display: inline-block; letter-spacing: 2px;">{otp}</h2>
        <p>This code will expire in 10 minutes.</p>
        <p>If you didn't create an account, you can safely ignore this email.</p>
        <p>Thanks,<br>The Growcommerce Team</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(body, 'html'))

    try:
        if smtp_port == 465:
            # SSL
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
        else:
            # TLS
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
        logger.info(f"OTP email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email to {to_email}: {str(e)}")
        return False


