#!/usr/bin/env python3
"""
Simple Voice to Harvey Bridge
A simplified version that runs voice_assistant and passes the result directly to Harvey.
"""

import os
import sys
from pathlib import Path

# Add HarveyConversation project to path
harvey_conversation_path = Path(__file__).parent.parent / "HarveyConversation"
sys.path.insert(0, str(harvey_conversation_path))

# Add current Harvey project to path
harvey_project_path = Path(__file__).parent
sys.path.insert(0, str(harvey_project_path))


def run_voice_and_harvey():
    """
    Simple function that runs voice assistant and then Harvey with the result.
    """
    print("🎤 Starting voice conversation...")

    try:
        # Import and run voice assistant
        from voice_assistant import voice_assistant

        # Run voice conversation
        result = voice_assistant(
            record_seconds=8,
            auto_analyze=True,
            save_transcript=True,
            save_analysis=True,
        )

        print(f"\n✅ Voice conversation completed with status: {result.get('status')}")

        # Extract the task from the conversation
        task = "Help me with a computer task"  # Default task

        # Try to get action items first
        action_items = result.get("action_items", [])
        if action_items:
            task = action_items[0]
            print(f"🎯 Using action item: {task}")
        else:
            # Fall back to last user message
            transcript = result.get("transcript", [])
            if transcript:
                user_messages = [
                    entry for entry in transcript if entry.get("speaker") == "User"
                ]
                if user_messages:
                    task = user_messages[-1]["message"]
                    print(f"🎯 Using last user message: {task}")

        # Now run Harvey with the extracted task
        print(f"\n🤖 Running Harvey with task: {task}")
        print("-" * 40)

        from harvey import Harvey

        harvey = Harvey()
        harvey.run(task)

        print("\n🎉 Complete! Voice conversation processed and Harvey task executed.")

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure HarveyConversation project is in the parent directory")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    # Check for API key
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("❌ Please set GOOGLE_API_KEY or GEMINI_API_KEY")
        sys.exit(1)

    run_voice_and_harvey()
