import os
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import aiosmtplib


class EmailService:
    @staticmethod
    async def _send_email(
        *,
        to_email: str,
        subject: str,
        plain_body: str,
        html_body: str,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> None:
        smtp_host = EmailService._get_env("SMTP_HOST")
        smtp_port = EmailService._get_env("SMTP_PORT")
        smtp_username = EmailService._get_env("SMTP_USERNAME")
        smtp_password = EmailService._get_env("SMTP_PASSWORD")
        smtp_from = EmailService._get_env("SMTP_FROM_EMAIL")

        if not smtp_host or not smtp_port or not smtp_from:
            raise RuntimeError(
                "Email SMTP is not configured. Set SMTP_HOST, SMTP_PORT, and SMTP_FROM_EMAIL."
            )

        try:
            port_int = int(smtp_port)
        except ValueError as exc:
            raise RuntimeError("SMTP_PORT must be an integer") from exc

        msg = EmailMessage()
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=False)

        smtp_from_domain = smtp_from.split("@")[-1] if "@" in smtp_from else None
        msg["Message-ID"] = make_msgid(domain=smtp_from_domain)

        reply_to = EmailService._get_env("SMTP_REPLY_TO", smtp_from)
        if reply_to:
            msg["Reply-To"] = reply_to

        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype="html")
        for filename, content, content_type in attachments or []:
            maintype, _, subtype = (content_type or "application/octet-stream").partition("/")
            if not subtype:
                maintype = "application"
                subtype = "octet-stream"
            msg.add_attachment(
                content,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )

        timeout = 15
        server = aiosmtplib.SMTP(
            hostname=smtp_host,
            port=port_int,
            timeout=timeout,
            use_tls=False,
            start_tls=False,
        )

        try:
            await server.connect(timeout=timeout)

            try:
                await server.starttls(timeout=timeout)
            except Exception:
                pass

            if smtp_username and smtp_password:
                await server.login(smtp_username, smtp_password, timeout=timeout)

            await server.send_message(msg, timeout=timeout)

        finally:
            try:
                await server.quit()
            except Exception:
                pass

    @staticmethod
    def _get_env(name: str, default: str | None = None) -> str | None:
        val = os.getenv(name)
        if val is None or str(val).strip() == "":
            return default
        return val

    @staticmethod
    async def send_email_verification_otp_email(
        *,
        to_email: str,
        otp_code: str,
        expires_in_minutes: int,
    ) -> None:
        """Send email verification OTP via SMTP."""
        subject = "NMK Job Portal - Email Verification OTP"

        plain_body = f"""
NMK JOB PORTAL

Email Verification OTP

Your OTP Code: {otp_code}

This OTP is valid for {expires_in_minutes} minutes.

If you did not request this OTP, please ignore this email.
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NMK Job Portal OTP</title>
</head>
<body style="margin:0;padding:0;background:#eef2f7;font-family:Arial, Helvetica, sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="center" style="padding:40px 15px;">

<table width="600" cellpadding="0" cellspacing="0" border="0"
style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 25px rgba(0,0,0,0.08);">

<tr>
<td align="center" style="background:linear-gradient(135deg,#003366,#0056b3);padding:35px 20px;">
<h1 style="color:#ffffff;margin:0;font-size:28px;font-weight:700;">NMK Job Portal</h1>
<p style="color:#dbe8ff;margin-top:8px;font-size:14px;">Secure Email Verification</p>
</td>
</tr>

<tr>
<td style="padding:40px 35px;">
<h2 style="margin-top:0;color:#1f2937;text-align:center;">Email Verification OTP</h2>
<p style="color:#4b5563;font-size:15px;line-height:24px;text-align:center;">
Use the verification code below to complete your registration.
</p>

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:25px 0;">
    <tr>
        <td align="center">

            <table cellpadding="0" cellspacing="0" border="0">
                <tr>
                    <td
                        align="center"
                        style="
                            background:#f4f8ff;
                            border:2px dashed #0056b3;
                            border-radius:12px;
                            padding:20px 35px;
                        "
                    >
                        <span
                            style="
                                font-size:36px;
                                font-weight:bold;
                                letter-spacing:10px;
                                color:#003366;
                                display:block;
                            "
                        >
                            {otp_code}
                        </span>
                    </td>
                </tr>
            </table>

        </td>
    </tr>
</table>

<p style="text-align:center;color:#4b5563;font-size:15px;">
This OTP will expire in <strong>{expires_in_minutes} minutes</strong>.
</p>

</td>
</tr>

<tr>
<td style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e5e7eb;">
<p style="margin:0;color:#6b7280;font-size:12px;">© NMK Job Portal. All Rights Reserved.</p>
<p style="margin-top:8px;color:#9ca3af;font-size:11px;">This is an automated email. Please do not reply.</p>
</td>
</tr>

</table>

</td>
</tr>
</table>

</body>
</html>
"""

        await EmailService._send_email(
            to_email=to_email,
            subject=subject,
            plain_body=plain_body,
            html_body=html_body,
        )


    

    @staticmethod
    async def send_password_reset_otp_email(
        *,
        to_email: str,
        otp_code: str,
        expires_in_minutes: int,
    ) -> None:
        """Send password reset OTP email via SMTP."""

        subject = "NMK Job Portal - Password Reset OTP"

        plain_body = f"""
NMK JOB PORTAL

Password Reset OTP

Your OTP Code: {otp_code}

This OTP is valid for {expires_in_minutes} minutes.

If you did not request this OTP, please ignore this email.
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NMK Job Portal OTP</title>
</head>

<body style="
    margin:0;
    padding:0;
    background:#eef2f7;
    font-family:Arial, Helvetica, sans-serif;
">

<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="center" style="padding:40px 15px;">

<table width="600" cellpadding="0" cellspacing="0" border="0"
style="
    background:#ffffff;
    border-radius:16px;
    overflow:hidden;
    box-shadow:0 8px 25px rgba(0,0,0,0.08);
">

    <!-- Header -->
    <tr>
        <td align="center"
            style="
                background:linear-gradient(135deg,#003366,#0056b3);
                padding:35px 20px;
            ">
            <h1 style="
                color:#ffffff;
                margin:0;
                font-size:28px;
                font-weight:700;
            ">
                NMK Job Portal
            </h1>

            <p style="
                color:#dbe8ff;
                margin-top:8px;
                font-size:14px;
            ">
                Secure Password Recovery
            </p>
        </td>
    </tr>

    <!-- Content -->
    <tr>
        <td style="padding:40px 35px;">

            <h2 style="
                margin-top:0;
                color:#1f2937;
                text-align:center;
            ">
                Password Reset OTP
            </h2>

            <p style="
                color:#4b5563;
                font-size:15px;
                line-height:24px;
                text-align:center;
            ">
                We received a request to reset your password.
                Use the verification code below to continue.
            </p>

            <!-- OTP Box -->
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td align="center">

                        <div style="
                            display:inline-block;
                            background:#f4f8ff;
                            border:2px dashed #0056b3;
                            border-radius:12px;
                            padding:20px 35px;
                            margin:25px 0;
                        ">
                            <span style="
                                font-size:36px;
                                font-weight:bold;
                                letter-spacing:10px;
                                color:#003366;
                            ">
                                {otp_code}
                            </span>
                        </div>

                    </td>
                </tr>
            </table>

            <p style="
                text-align:center;
                color:#4b5563;
                font-size:15px;
            ">
                This OTP will expire in
                <strong>{expires_in_minutes} minutes</strong>.
            </p>

            <div style="
                background:#fff8e6;
                border-left:4px solid #f59e0b;
                padding:12px 15px;
                margin-top:25px;
                border-radius:6px;
            ">
                <p style="
                    margin:0;
                    color:#92400e;
                    font-size:14px;
                    line-height:22px;
                ">
                    For security reasons, never share this OTP with anyone.
                </p>
            </div>

        </td>
    </tr>

    <!-- Footer -->
    <tr>
        <td style="
            background:#f8fafc;
            padding:20px;
            text-align:center;
            border-top:1px solid #e5e7eb;
        ">
            <p style="
                margin:0;
                color:#6b7280;
                font-size:12px;
            ">
                © NMK Job Portal. All Rights Reserved.
            </p>

            <p style="
                margin-top:8px;
                color:#9ca3af;
                font-size:11px;
            ">
                This is an automated email. Please do not reply.
            </p>
        </td>
    </tr>

</table>

</td>
</tr>
</table>

</body>
</html>
"""

        await EmailService._send_email(
            to_email=to_email,
            subject=subject,
            plain_body=plain_body,
            html_body=html_body,
        )

    @staticmethod
    async def send_userid_email(
        recipient_email: str,
        user_id: str
    ):
        login_page_url = EmailService._get_env(
            "LOGIN_PAGE_URL",
            "https://NMK_jobportal.com/login"
        )

        subject = (
            "NMK Job Portal Account Recovery - User ID Information"
        )

        plain_body = f"""
Hello,

We received a request to retrieve the User ID associated with your NMK Job Portal account.

Your Login Email:
{user_id}

Login Page:
{login_page_url}

If you did not request this information, no further action is required and you may safely ignore this email.

Regards,
NMK Job Portal Support Team
"""

        html_body = f"""
<html>
<body style="font-family: Arial, Helvetica, sans-serif; color: #333333;">

    <h2>Account Recovery Request</h2>

    <p>
        We received a request to retrieve the Login EmailS associated with your
        NMK Job Portal account.
    </p>

    <p>
        <strong>Your Login Email:</strong><br>
        {user_id}
    </p>

    <p>
        <a
            href="{login_page_url}"
            style="
                background-color:#0d6efd;
                color:#ffffff;
                padding:10px 20px;
                text-decoration:none;
                border-radius:4px;
                display:inline-block;
                font-weight:bold;
            "
        >
            Click Here to Login
        </a>
    </p>

    <p>
        If you did not request this information,
        no further action is required and you may safely ignore this email.
    </p>

    <hr>

    <p style="font-size:12px;color:#666666;">
        This is an automated email. Please do not reply directly to this message.
    </p>

    <p>
        Regards,<br>
        <strong>NMK Job Portal Support Team</strong>
    </p>

</body>
</html>
"""

        await EmailService._send_email(
            to_email=recipient_email,
            subject=subject,
            plain_body=plain_body,
            html_body=html_body,
        )

    @staticmethod
    async def send_interview_scheduled_email(
        *,
        to_email: str,
        candidate_name: str,
        interview_title: str | None = None,
        company_name: str,
        employer_name: str | None = None,
        job_title: str,
        interview_round: str,
        interview_date: str,
        interview_time: str,
        start_time: str | None = None,
        end_time: str | None = None,
        timezone: str | None = None,
        mode: str,
        meeting_link_or_location: str,
        interviewer: str,
        remarks: str,
        include_remarks: bool = True,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> None:
        subject = "NMK Job Portal - Interview Scheduled"

        plain_body = EmailService._build_interview_plain_body(
            title="Interview Scheduled",
            candidate_name=candidate_name,
            interview_title=interview_title,
            company_name=company_name,
            employer_name=employer_name,
            job_title=job_title,
            interview_round=interview_round,
            interview_date=interview_date,
            interview_time=interview_time,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
            mode=mode,
            meeting_link_or_location=meeting_link_or_location,
            interviewer=interviewer,
            remarks=remarks,
            include_remarks=include_remarks,
        )

        html_body = EmailService._build_interview_html_body(
            title="Interview Scheduled",
            subtitle="Your interview has been scheduled",
            candidate_name=candidate_name,
            interview_title=interview_title,
            company_name=company_name,
            employer_name=employer_name,
            job_title=job_title,
            interview_round=interview_round,
            interview_date=interview_date,
            interview_time=interview_time,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
            mode=mode,
            meeting_link_or_location=meeting_link_or_location,
            interviewer=interviewer,
            remarks=remarks,
            include_remarks=include_remarks,
        )

        await EmailService._send_email(
            to_email=to_email,
            subject=subject,
            plain_body=plain_body,
            html_body=html_body,
            attachments=attachments,
        )

    @staticmethod
    async def send_interview_rescheduled_email(
        *,
        to_email: str,
        candidate_name: str,
        interview_title: str | None = None,
        company_name: str,
        employer_name: str | None = None,
        job_title: str,
        interview_round: str,
        interview_date: str,
        interview_time: str,
        start_time: str | None = None,
        end_time: str | None = None,
        timezone: str | None = None,
        mode: str,
        meeting_link_or_location: str,
        interviewer: str,
        remarks: str,
        include_remarks: bool = True,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> None:
        subject = "NMK Job Portal - Interview Rescheduled"

        plain_body = EmailService._build_interview_plain_body(
            title="Interview Rescheduled",
            candidate_name=candidate_name,
            interview_title=interview_title,
            company_name=company_name,
            employer_name=employer_name,
            job_title=job_title,
            interview_round=interview_round,
            interview_date=interview_date,
            interview_time=interview_time,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
            mode=mode,
            meeting_link_or_location=meeting_link_or_location,
            interviewer=interviewer,
            remarks=remarks,
            include_remarks=include_remarks,
        )

        html_body = EmailService._build_interview_html_body(
            title="Interview Rescheduled",
            subtitle="Your interview details have been updated",
            candidate_name=candidate_name,
            interview_title=interview_title,
            company_name=company_name,
            employer_name=employer_name,
            job_title=job_title,
            interview_round=interview_round,
            interview_date=interview_date,
            interview_time=interview_time,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
            mode=mode,
            meeting_link_or_location=meeting_link_or_location,
            interviewer=interviewer,
            remarks=remarks,
            include_remarks=include_remarks,
        )

        await EmailService._send_email(
            to_email=to_email,
            subject=subject,
            plain_body=plain_body,
            html_body=html_body,
            attachments=attachments,
        )

    @staticmethod
    async def send_interview_cancelled_email(
        *,
        to_email: str,
        candidate_name: str,
        interview_title: str | None = None,
        company_name: str,
        employer_name: str | None = None,
        job_title: str,
        interview_round: str,
        interview_date: str,
        interview_time: str,
        start_time: str | None = None,
        end_time: str | None = None,
        timezone: str | None = None,
        mode: str,
        meeting_link_or_location: str,
        interviewer: str,
        remarks: str,
        include_remarks: bool = True,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> None:
        subject = "NMK Job Portal - Interview Cancelled"

        plain_body = EmailService._build_interview_plain_body(
            title="Interview Cancelled",
            candidate_name=candidate_name,
            interview_title=interview_title,
            company_name=company_name,
            employer_name=employer_name,
            job_title=job_title,
            interview_round=interview_round,
            interview_date=interview_date,
            interview_time=interview_time,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
            mode=mode,
            meeting_link_or_location=meeting_link_or_location,
            interviewer=interviewer,
            remarks=remarks,
            include_remarks=include_remarks,
        )

        html_body = EmailService._build_interview_html_body(
            title="Interview Cancelled",
            subtitle="Your interview has been cancelled",
            candidate_name=candidate_name,
            interview_title=interview_title,
            company_name=company_name,
            employer_name=employer_name,
            job_title=job_title,
            interview_round=interview_round,
            interview_date=interview_date,
            interview_time=interview_time,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
            mode=mode,
            meeting_link_or_location=meeting_link_or_location,
            interviewer=interviewer,
            remarks=remarks,
            include_remarks=include_remarks,
        )

        await EmailService._send_email(
            to_email=to_email,
            subject=subject,
            plain_body=plain_body,
            html_body=html_body,
            attachments=attachments,
        )

    @staticmethod
    def _build_interview_plain_body(
        *,
        title: str,
        candidate_name: str,
        interview_title: str | None,
        company_name: str,
        employer_name: str | None,
        job_title: str,
        interview_round: str,
        interview_date: str,
        interview_time: str,
        start_time: str | None,
        end_time: str | None,
        timezone: str | None,
        mode: str,
        meeting_link_or_location: str,
        interviewer: str,
        remarks: str,
        include_remarks: bool,
    ) -> str:
        remarks_line = (
            f"Remarks: {remarks}\n"
            if include_remarks
            else ""
        )

        return f"""
NMK JOB PORTAL

{title}

Interview Title: {interview_title or title}
Candidate Name: {candidate_name}
Company Name: {company_name}
Employer Name: {employer_name or company_name}
Job Title: {job_title}
Interview Round: {interview_round}
Interview Date: {interview_date}
Start Time: {start_time or interview_time}
End Time: {end_time or "N/A"}
Timezone: {timezone or "UTC"}
Mode: {mode}
Meeting Link: {meeting_link_or_location}
Assigned Interviewers: {interviewer}

{remarks_line}
Regards,
NMK Job Portal Support Team
"""

    @staticmethod
    def _build_interview_html_body(
        *,
        title: str,
        subtitle: str,
        candidate_name: str,
        interview_title: str | None,
        company_name: str,
        employer_name: str | None,
        job_title: str,
        interview_round: str,
        interview_date: str,
        interview_time: str,
        start_time: str | None,
        end_time: str | None,
        timezone: str | None,
        mode: str,
        meeting_link_or_location: str,
        interviewer: str,
        remarks: str,
        include_remarks: bool,
    ) -> str:
        remarks_row = (
            f"<tr><td><strong>Remarks</strong></td><td>{remarks}</td></tr>"
            if include_remarks
            else ""
        )

        return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NMK Job Portal Interview</title>
</head>
<body style="margin:0;padding:0;background:#eef2f7;font-family:Arial, Helvetica, sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="center" style="padding:40px 15px;">

<table width="600" cellpadding="0" cellspacing="0" border="0"
style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 25px rgba(0,0,0,0.08);">

<tr>
<td align="center" style="background:linear-gradient(135deg,#003366,#0056b3);padding:35px 20px;">
<h1 style="color:#ffffff;margin:0;font-size:28px;font-weight:700;">NMK Job Portal</h1>
<p style="color:#ffffff;margin-top:8px;font-size:16px;font-weight:500;">{subtitle}</p>
</td>
</tr>

<tr>
<td style="padding:40px 35px;">
<h2 style="margin-top:0;color:#1f2937;text-align:center;">{title}</h2>

<table width="100%" cellpadding="8" cellspacing="0" border="0" style="color:#4b5563;font-size:15px;line-height:24px;">
<tr><td><strong>Interview Title</strong></td><td>{interview_title or title}</td></tr>
<tr><td><strong>Candidate Name</strong></td><td>{candidate_name}</td></tr>
<tr><td><strong>Company Name</strong></td><td>{company_name}</td></tr>
<tr><td><strong>Employer Name</strong></td><td>{employer_name or company_name}</td></tr>
<tr><td><strong>Job Title</strong></td><td>{job_title}</td></tr>
<tr><td><strong>Interview Round</strong></td><td>{interview_round}</td></tr>
<tr><td><strong>Interview Date</strong></td><td>{interview_date}</td></tr>
<tr><td><strong>Start Time</strong></td><td>{start_time or interview_time}</td></tr>
<tr><td><strong>End Time</strong></td><td>{end_time or "N/A"}</td></tr>
<tr><td><strong>Timezone</strong></td><td>{timezone or "UTC"}</td></tr>
<tr><td><strong>Mode</strong></td><td>{mode}</td></tr>
<tr><td><strong>Meeting Link</strong></td><td>{meeting_link_or_location}</td></tr>
<tr><td><strong>Assigned Interviewers</strong></td><td>{interviewer}</td></tr>
{remarks_row}
</table>

</td>
</tr>

<tr>
<td style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e5e7eb;">
<p style="margin:0;color:#6b7280;font-size:12px;">Â© NMK Job Portal. All Rights Reserved.</p>
<p style="margin-top:8px;color:#9ca3af;font-size:11px;">This is an automated email. Please do not reply.</p>
</td>
</tr>

</table>

</td>
</tr>
</table>

</body>
</html>
"""

    @staticmethod
    async def send_job_alert_email(
        *,
        to_email: str,
        candidate_name: str,
        company_name: str,
        job_title: str,
        location: str,
        employment_type: str,
        experience_required: str,
        application_deadline: str | None,
    ) -> None:
        subject = "New Job Matching Your Alert"

        plain_body = f"""
    Hello {candidate_name},

    A new job matching your alert has been posted.

    Job Title: {job_title}
    Company: {company_name}
    Location: {location}
    Employment Type: {employment_type}
    Experience Required: {experience_required}
    Application Deadline: {application_deadline or "Not Specified"}

    Login to the NMK Job Portal to apply.

    Regards,
    NMK Job Portal Team
    """

        html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    </head>

    <body style="font-family:Arial,Helvetica,sans-serif;background:#eef2f7;padding:30px;">

    <div style="max-width:650px;background:white;margin:auto;border-radius:10px;padding:30px;">

    <h2 style="color:#003366;">
    New Job Matching Your Alert
    </h2>

    <p>Hello <strong>{candidate_name}</strong>,</p>

    <p>
    A new job matching your saved job alert has been posted.
    </p>

    <table cellpadding="8">

    <tr>
    <td><strong>Job Title</strong></td>
    <td>{job_title}</td>
    </tr>

    <tr>
    <td><strong>Company</strong></td>
    <td>{company_name}</td>
    </tr>

    <tr>
    <td><strong>Location</strong></td>
    <td>{location}</td>
    </tr>

    <tr>
    <td><strong>Employment Type</strong></td>
    <td>{employment_type}</td>
    </tr>

    <tr>
    <td><strong>Experience Required</strong></td>
    <td>{experience_required}</td>
    </tr>

    <tr>
    <td><strong>Application Deadline</strong></td>
    <td>{application_deadline or "Not Specified"}</td>
    </tr>

    </table>

    <p style="margin-top:25px;">
    Please login to the NMK Job Portal to apply for this opportunity.
    </p>

    <hr>

    <p style="font-size:12px;color:#888;">
    This is an automated email. Please do not reply.
    </p>

    </div>

    </body>
    </html>
    """

        await EmailService._send_email(
            to_email=to_email,
            subject=subject,
            plain_body=plain_body,
            html_body=html_body,
        )

    @staticmethod
    async def send_job_alert_summary_email(
        *,
        to_email: str,
        candidate_name: str,
        jobs: list,
    ) -> None:
        subject = "New Jobs Matching Your Job Alert"
        lines = []
        rows = []
        for index, job in enumerate(jobs, start=1):
            title = getattr(job, "title", "Not Specified")
            company = getattr(job, "company_name", "Not Specified")
            location = getattr(job, "location", "Not Specified")
            employment_type = getattr(job, "employment_type", "Not Specified")
            lines.append(
                f"{index}. {title} | {company} | {location} | {employment_type}"
            )
            rows.append(
                "<tr>"
                f"<td>{index}</td>"
                f"<td>{title}</td>"
                f"<td>{company}</td>"
                f"<td>{location}</td>"
                f"<td>{employment_type}</td>"
                "</tr>"
            )

        plain_body = f"""
Hello {candidate_name},

The following jobs matched your Job Alert.

{chr(10).join(lines)}

Login to the NMK Job Portal to view all matching jobs.

Regards,
NMK Job Portal Team
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,Helvetica,sans-serif;background:#eef2f7;padding:30px;">
<div style="max-width:760px;background:white;margin:auto;border-radius:10px;padding:30px;">
<h2 style="color:#003366;">New Jobs Matching Your Job Alert</h2>
<p>Hello <strong>{candidate_name}</strong>,</p>
<p>The following jobs matched your Job Alert.</p>
<table cellpadding="8" cellspacing="0" style="width:100%;border-collapse:collapse;">
<thead>
<tr>
<th align="left">#</th>
<th align="left">Job Title</th>
<th align="left">Company</th>
<th align="left">Location</th>
<th align="left">Employment Type</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
<p style="margin-top:25px;">Login to the NMK Job Portal to view all matching jobs.</p>
</div>
</body>
</html>
"""

        await EmailService._send_email(
            to_email=to_email,
            subject=subject,
            plain_body=plain_body,
            html_body=html_body,
        )

    @staticmethod
    async def send_contact_support_email(
        *,
        full_name: str,
        email: str,
        phone_number: str | None,
        inquiry_type: str,
        subject: str,
        message: str,
    ) -> None:
        """Send Contact Us inquiry to the support team."""

        support_email = EmailService._get_env(
            "CONTACT_SUPPORT_EMAIL",
            "info@nmkglobalinc.com",
        )

        email_subject = f"NMK Job Portal | Contact Us | {subject}"

        plain_body = f"""
New Contact Us Inquiry

Name:
{full_name}

Email:
{email}

Phone Number:
{phone_number or "N/A"}

Inquiry Type:
{inquiry_type}

Subject:
{subject}

Message:
{message}
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, Helvetica, sans-serif;">

<h2>New Contact Us Inquiry</h2>

<table cellpadding="8" cellspacing="0" border="0">

<tr>
<td><strong>Name</strong></td>
<td>{full_name}</td>
</tr>

<tr>
<td><strong>Email</strong></td>
<td>{email}</td>
</tr>

<tr>
<td><strong>Phone</strong></td>
<td>{phone_number or "N/A"}</td>
</tr>

<tr>
<td><strong>Inquiry Type</strong></td>
<td>{inquiry_type}</td>
</tr>

<tr>
<td><strong>Subject</strong></td>
<td>{subject}</td>
</tr>

<tr>
<td valign="top"><strong>Message</strong></td>
<td>{message}</td>
</tr>

</table>

</body>
</html>
"""

        await EmailService._send_email(
            to_email=support_email,
            subject=email_subject,
            plain_body=plain_body,
            html_body=html_body,
        )

    
    @staticmethod
    async def send_contact_acknowledgement_email(
        *,
        full_name: str,
        email: str,
        subject: str,
        message: str,
    ) -> None:
        """Send acknowledgement email to the user."""

        email_subject = "NMK Job Portal | Contact Us Acknowledgement"
        plain_body = f"""
Dear {full_name},

Thank you for contacting NMK Job Portal.

We have successfully received your inquiry.

Subject:
{subject}

Message:
{message}

Our support team will review your request and get back to you as soon as possible.

Regards,
NMK Job Portal Support Team
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<body style="
font-family:Arial,Helvetica,sans-serif;
background:#f8fafc;
padding:30px;
">

<div style="
max-width:650px;
margin:auto;
background:#ffffff;
border-radius:10px;
padding:30px;
border:1px solid #e5e7eb;
">

<h2 style="color:#003366;">
Thank You for Contacting NMK Job Portal
</h2>

<p>
Hello <strong>{full_name}</strong>,
</p>

<p>
We have successfully received your inquiry.
</p>

<table cellpadding="8">

<tr>
<td><strong>Subject</strong></td>
<td>{subject}</td>
</tr>

<tr>
<td valign="top"><strong>Message</strong></td>
<td>{message}</td>
</tr>

</table>

<p style="margin-top:25px;">
Our support team will review your inquiry and contact you shortly.
</p>

<br>

<p>
Regards,<br>
<b>NMK Job Portal Support Team</b>
</p>

<hr>

<p style="font-size:12px;color:#888888;">
This is an automated acknowledgement email.
Please do not reply directly to this email.
</p>

</div>

</body>
</html>
"""

        await EmailService._send_email(
            to_email=email,
            subject=email_subject,
            plain_body=plain_body,
            html_body=html_body,
        )
