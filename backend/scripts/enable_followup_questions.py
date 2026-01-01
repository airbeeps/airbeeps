#!/usr/bin/env python3
"""
Script to enable follow-up questions feature in the system configuration.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from airbeeps.database import get_async_session
from airbeeps.system_config.api.v1.schemas import ConfigUpdate
from airbeeps.system_config.service import config_service


async def enable_followup_questions():
    """Enable follow-up questions in system config."""
    async for session in get_async_session():
        # Enable follow-up questions
        update1 = ConfigUpdate(value=True)
        await config_service.update_config(
            session, "ui_generate_followup_questions", update1
        )

        # Set count to 3 (default)
        update2 = ConfigUpdate(value=3)
        await config_service.update_config(
            session, "ui_followup_question_count", update2
        )

        await session.commit()
        print("[OK] Follow-up questions enabled!")
        print("[OK] Follow-up question count set to 3")

        # Verify
        enabled = await config_service.get_config_value(
            session, "ui_generate_followup_questions"
        )
        count = await config_service.get_config_value(
            session, "ui_followup_question_count"
        )
        print("\nCurrent settings:")
        print(f"  - Enabled: {enabled}")
        print(f"  - Count: {count}")


if __name__ == "__main__":
    asyncio.run(enable_followup_questions())
