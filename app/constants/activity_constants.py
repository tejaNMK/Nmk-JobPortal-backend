from enum import Enum


class ActivityType(str, Enum):
    JOB_CREATED = "JOB_CREATED"
    JOB_UPDATED = "JOB_UPDATED"
    JOB_DELETED = "JOB_DELETED"
    JOB_CLOSED = "JOB_CLOSED"
    DUPLICATE_JOB_ATTEMPT = "DUPLICATE_JOB_ATTEMPT"
    ACTIVITY_RECORDED = "ACTIVITY_RECORDED"


ACTIVITY_MESSAGE_VERBS = {
    ActivityType.JOB_CREATED: "Created job",
    ActivityType.JOB_UPDATED: "Updated job",
    ActivityType.JOB_DELETED: "Deleted job",
    ActivityType.JOB_CLOSED: "Closed job",
    ActivityType.DUPLICATE_JOB_ATTEMPT: "Duplicate job attempt",
    ActivityType.ACTIVITY_RECORDED: "Recorded activity",
}
