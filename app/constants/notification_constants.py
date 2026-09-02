"""
Notification-related constants used across the application.
"""


class NotificationPreference:
    # These must match JobAlertNotificationPreference in candidate_schema.py —
    # that's the literal type actually validated/stored on JobAlert rows.
    EMAIL = "EMAIL"
    IN_APP = "IN_APP"
    BOTH = "BOTH"

    @classmethod
    def normalize(cls, value, *, allow_legacy: bool = False) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().upper().replace("-", "_").replace(" ", "_")
        aliases = {
            "EMAIL": cls.EMAIL,
            "IN_APP": cls.IN_APP,
            "INAPP": cls.IN_APP,
            "BOTH": cls.BOTH,
            "EMAIL_AND_IN_APP": cls.BOTH,
            "EMAIL_IN_APP": cls.BOTH,
            "EMAIL_AND_INAPP": cls.BOTH,
        }
        if allow_legacy:
            aliases.update(
                {
                    "PORTAL": cls.IN_APP,
                    "PORTAL_NOTIFICATION": cls.IN_APP,
                    "IN_APP_NOTIFICATION": cls.IN_APP,
                }
            )
        return aliases.get(normalized, normalized)


class NotificationFrequency:
    INSTANT = "INSTANT"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"

    @classmethod
    def normalize(cls, value, *, default: str | None = None) -> str | None:
        if value is None:
            return default
        normalized = str(value).strip().upper().replace("-", "_").replace(" ", "_")
        aliases = {
            "INSTANT": cls.INSTANT,
            "INSTANTLY": cls.INSTANT,
            "DAILY": cls.DAILY,
            "WEEKLY": cls.WEEKLY,
        }
        return aliases.get(normalized, normalized)


class NotificationChannel:
    EMAIL = "EMAIL"
    IN_APP = "IN_APP"


class NotificationDeliveryStatus:
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class NotificationType:
    JOB_ALERT = "JOB_ALERT"
    JOB_PUBLISHED = "JOB_PUBLISHED"
    JOB_CLOSED = "JOB_CLOSED"
    JOB_EXPIRED = "JOB_EXPIRED"
    JOB_EDITED = "JOB_EDITED"
    JOB_APPROVAL = "JOB_APPROVAL"
    INTERVIEW = "INTERVIEW"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    INTERVIEW_RESCHEDULED = "INTERVIEW_RESCHEDULED"
    INTERVIEW_CANCELLED = "INTERVIEW_CANCELLED"
    INTERVIEW_REMINDER = "INTERVIEW_REMINDER"
    INTERVIEW_COMPLETED = "INTERVIEW_COMPLETED"
    CANDIDATE_ACCEPTED_INTERVIEW = "CANDIDATE_ACCEPTED_INTERVIEW"
    CANDIDATE_DECLINED_INTERVIEW = "CANDIDATE_DECLINED_INTERVIEW"
    SHORTLIST = "SHORTLIST"
    APPLICATION_STATUS = "APPLICATION_STATUS"
    APPLICATION_RECEIVED = "APPLICATION_RECEIVED"
    APPLICATION_WITHDRAWN = "APPLICATION_WITHDRAWN"
    APPLICATION_SHORTLISTED = "APPLICATION_SHORTLISTED"
    APPLICATION_REJECTED = "APPLICATION_REJECTED"
    APPLICATION_HIRED = "APPLICATION_HIRED"
    INVITATION_ACCEPTED = "INVITATION_ACCEPTED"
    INVITATION_REJECTED = "INVITATION_REJECTED"
    CANDIDATE_INVITATION = "CANDIDATE_INVITATION"
    PACKAGE_PURCHASED = "PACKAGE_PURCHASED"
    PACKAGE_EXPIRING = "PACKAGE_EXPIRING"
    CREDITS_LOW = "CREDITS_LOW"
    SUBSCRIPTION_EXPIRING = "SUBSCRIPTION_EXPIRING"
    SUBSCRIPTION_RENEWED = "SUBSCRIPTION_RENEWED"
    RESUME_DOWNLOADED = "RESUME_DOWNLOADED"
    EMPLOYER_PROFILE_APPROVED = "EMPLOYER_PROFILE_APPROVED"
    EMPLOYER_VERIFICATION = "EMPLOYER_VERIFICATION"
    SYSTEM_ANNOUNCEMENT = "SYSTEM_ANNOUNCEMENT"
    ADMIN_ANNOUNCEMENT = "ADMIN_ANNOUNCEMENT"
    SUPPORT_TICKET_UPDATED = "SUPPORT_TICKET_UPDATED"
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
    MOBILE_VERIFICATION = "MOBILE_VERIFICATION"
    APPLICATION_NUDGE = "APPLICATION_NUDGE"


class ReferenceType:
    JOB = "JOB"
    INTERVIEW = "INTERVIEW"
    APPLICATION = "APPLICATION"
    CANDIDATE = "CANDIDATE"
    INVITATION = "INVITATION"
    VERIFICATION = "VERIFICATION"
    SUBSCRIPTION = "SUBSCRIPTION"
    PACKAGE = "PACKAGE"
    SUPPORT_TICKET = "SUPPORT_TICKET"
    ANNOUNCEMENT = "ANNOUNCEMENT"


class NotificationTitle:
    JOB_ALERT = "New Job Alert"
    DAILY_JOB_ALERT = "Daily Job Alert Summary"
    WEEKLY_JOB_ALERT = "Weekly Job Alert Summary"

    INTERVIEW = "Interview Scheduled"
    INTERVIEW_RESCHEDULED = "Interview Rescheduled"
    INTERVIEW_CANCELLED = "Interview Cancelled"
    INTERVIEW_COMPLETED = "Interview Completed"
    SHORTLIST = "You've Been Shortlisted"
    APPLICATION_STATUS = "Application Status Updated"
    APPLICATION_RECEIVED = "New Application Received"
    APPLICATION_WITHDRAWN = "Application Withdrawn"
    APPLICATION_SHORTLISTED = "Application Shortlisted"
    APPLICATION_REJECTED = "Application Rejected"
    APPLICATION_HIRED = "Application Hired"
    INVITATION_ACCEPTED = "Invitation Accepted"
    INVITATION_REJECTED = "Invitation Rejected"
    SUBSCRIPTION_RENEWED = "Subscription Renewed"
    PACKAGE_PURCHASED = "Package Purchased"

    CANDIDATE_INVITATION = "Candidate Invitation"

    EMAIL_VERIFICATION = "Email Verification"
    MOBILE_VERIFICATION = "Mobile Verification"

    APPLICATION_NUDGE = "Candidate Follow-up"


class NotificationMessage:
    JOB_ALERT = (
        "A new job matching your job alert has been posted."
    )

    DAILY_JOB_ALERT = (
        "You have new job matches from the last 24 hours."
    )

    WEEKLY_JOB_ALERT = (
        "You have new job matches from the last 7 days."
    )

    INTERVIEW = (
        "An interview has been scheduled for your application."
    )

    SHORTLIST = (
        "Congratulations! You have been shortlisted for a job."
    )

    APPLICATION_STATUS = (
        "Your job application status has been updated."
    )

    APPLICATION_RECEIVED = (
        "{candidate_name} applied for {job_title}."
    )

    APPLICATION_WITHDRAWN = (
        "{candidate_name} withdrew their application for {job_title}."
    )
    APPLICATION_SHORTLISTED = (
        "You have been shortlisted for {job_title}."
    )
    APPLICATION_REJECTED = (
        "Your application for {job_title} was not selected."
    )
    APPLICATION_HIRED = (
        "Congratulations! You have been hired for {job_title}."
    )

    INVITATION_ACCEPTED = (
        "{candidate_name} accepted your invitation for {job_title}."
    )

    INVITATION_REJECTED = (
        "{candidate_name} declined your invitation for {job_title}."
    )

    CANDIDATE_INVITATION = (
        "You have received a new candidate invitation."
    )

    EMAIL_VERIFICATION = (
        "Please verify your email address."
    )

    MOBILE_VERIFICATION = (
        "Please verify your mobile number."
    )

    # {candidate_name}, {job_title}, and {applied_ago} are substituted by the
    # caller. Naming the candidate directly is what lets a recruiter tell
    # which applicant is following up without opening the application first.
    APPLICATION_NUDGE = (
        "{candidate_name} sent a follow-up on their application for {job_title} "
        "(applied {applied_ago}). They're checking in on their application status."
    )
