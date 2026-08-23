"""
AI Valet - Audit Logger

This file keeps a simple record of important actions performed by the
AI Valet system. The logs can be used later to understand what happened
and when it happened.

Only Python's built-in modules are used, so no extra package is needed.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path


# The log file will be created automatically.
LOG_FILE = Path("logs/audit_log.jsonl")


class AuditLogger:
    """Create and read simple audit logs for AI Valet."""

    def __init__(self, log_file=LOG_FILE):
        self.log_file = Path(log_file)

        # Make the logs folder if it does not already exist.
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _hide_private_data(self, value):
        """Hide a few common types of private information before logging."""

        if not isinstance(value, str):
            return value

        # Hide email addresses.
        value = re.sub(
            r"\b[\w.+-]+@[\w.-]+\.\w+\b",
            "[email hidden]",
            value
        )

        # Hide simple phone-number patterns.
        value = re.sub(
            r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)",
            "[phone hidden]",
            value
        )

        # Hide a couple of common API-key formats.
        value = re.sub(
            r"\b(?:sk-[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+)\b",
            "[API key hidden]",
            value
        )

        return value

    def _clean_details(self, data):
        """Clean private information inside dictionaries and lists."""

        if isinstance(data, str):
            return self._hide_private_data(data)

        if isinstance(data, dict):
            return {
                key: self._clean_details(value)
                for key, value in data.items()
            }

        if isinstance(data, list):
            return [self._clean_details(item) for item in data]

        return data

    def log(self, user_id, action, status, details=None):
        """
        Add one action to the audit log.

        Example actions:
        - EMAIL_CLASSIFICATION
        - AUTO_REPLY_GENERATION
        - PROMPT_VALIDATION
        - DATA_PROCESSING

        Status can be something like SUCCESS, FAILED, or BLOCKED.
        """

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": self._hide_private_data(str(user_id)),
            "action": self._hide_private_data(str(action)),
            "status": self._hide_private_data(str(status)),
            "details": self._clean_details(details or {})
        }

        with self.log_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

        return record

    def get_logs(self):
        """Return all saved audit logs."""

        if not self.log_file.exists():
            return []

        logs = []

        with self.log_file.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if not line:
                    continue

                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    # Ignore a damaged line instead of stopping the program.
                    continue

        return logs

    def find_logs(self, user_id=None, action=None, status=None):
        """Find logs using optional user, action, and status filters."""

        logs = self.get_logs()
        results = []

        for log in logs:
            if user_id is not None and log.get("user_id") != user_id:
                continue

            if action is not None and log.get("action") != action:
                continue

            if status is not None and log.get("status") != status:
                continue

            results.append(log)

        return results


def show_logs(logs):
    """Print audit logs in an easy-to-read format."""

    if not logs:
        print("No audit logs found.")
        return

    print("\n========== AI VALET AUDIT LOG ==========\n")

    for number, log in enumerate(logs, start=1):
        print(f"Log {number}")
        print(f"Time   : {log['timestamp']}")
        print(f"User   : {log['user_id']}")
        print(f"Action : {log['action']}")
        print(f"Status : {log['status']}")
        print(
            "Details:",
            json.dumps(log["details"], indent=2, ensure_ascii=False)
        )
        print("-" * 45)


def main():
    """Small example showing how the logger can be used."""

    logger = AuditLogger()

    # AI Valet successfully classified an email.
    logger.log(
        user_id="user_001",
        action="EMAIL_CLASSIFICATION",
        status="SUCCESS",
        details={
            "category": "Customer Support",
            "confidence": 0.94
        }
    )

    # An automatically generated reply was created.
    logger.log(
        user_id="user_001",
        action="AUTO_REPLY_GENERATION",
        status="SUCCESS",
        details={
            "reply_generated": True,
            "human_review": True
        }
    )

    # A suspicious prompt was stopped.
    logger.log(
        user_id="user_002",
        action="PROMPT_VALIDATION",
        status="BLOCKED",
        details={
            "reason": "Possible prompt injection",
            "risk": "HIGH"
        }
    )

    # Private information is hidden before it is written to the log.
    logger.log(
        user_id="user_003",
        action="DATA_PROCESSING",
        status="SUCCESS",
        details={
            "contact": "customer@example.com",
            "phone": "+91 9876543210"
        }
    )

    show_logs(logger.get_logs())


if __name__ == "__main__":
    main()
