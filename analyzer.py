"""
Conversation Analyzer - Extract Action Items from Transcripts
Analyzes conversation transcripts using Gemini Flash to identify actionable tasks.

Usage:
    python conversation_analyzer.py transcript_file.json
    python conversation_analyzer.py --latest  # Analyze the most recent transcript
"""

import json
import os
import argparse
import glob
from datetime import datetime
from pathlib import Path

import google.generativeai as genai

# Configuration - Replace with your actual API key
API_KEY = "AIzaSyDEpKgpwdgCem96MNiBJjjK4Dx6ISogHZA"
MODEL_NAME = "gemini-2.5-flash"

# Initialize Gemini Flash model for conversation analysis
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(MODEL_NAME)


def load_transcript(file_path):
    """Load and parse a transcript JSON file.

    Args:
        file_path (str): Path to the transcript JSON file

    Returns:
        dict: Parsed transcript data, or None if loading fails
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading transcript: {e}")
        return None


def extract_conversation_text(transcript_data):
    """Extract conversation text from transcript data structure.

    Processes transcript entries and formats them as speaker-text pairs,
    filtering out system messages and metadata.

    Args:
        transcript_data (dict): Parsed transcript JSON data

    Returns:
        str: Formatted conversation text with speaker labels
    """
    conversation = []

    for entry in transcript_data.get("transcript", []):
        if entry["type"] in ["user", "ai"]:
            speaker = entry["speaker"]
            text = entry["text"]
            timestamp = entry["timestamp"]
            conversation.append(f"{speaker}: {text}")

    return "\n".join(conversation)


def analyze_conversation(conversation_text):
    """Analyze conversation using Gemini Flash to extract actionable tasks.

    Sends the conversation text to Gemini Flash 2.5 with a specialized prompt
    designed to identify concrete, executable action items from dialogue.

    Args:
        conversation_text (str): Formatted conversation text

    Returns:
        str: List of action items or "None" if no clear actions found
    """

    prompt = f"""
Analyze the following conversation and extract specific actionable tasks that can be executed on a computer.

CONVERSATION:
{conversation_text}

Return ONLY a simple list of action items. Each action item should be a clear, specific task that can be executed.

If there are clear action items, return them as a numbered list like this:
1. Open Chrome browser
2. Navigate to Amazon.com
3. Search for wireless mouse under $30

If there are NO clear action items, return exactly: "None"

Focus on:
- Concrete tasks involving computer automation
- Opening specific applications or websites
- File operations
- System tasks
- Research or information gathering with specific targets

Be specific and practical. Only include tasks that are clearly actionable based on what was discussed.
"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return None


def find_latest_transcript():
    """Find the most recently modified transcript file.

    Searches for transcript_*.json files in the current directory
    and returns the one with the latest modification time.

    Returns:
        str: Path to latest transcript file, or None if none found
    """
    transcript_files = glob.glob("transcript_*.json")
    if not transcript_files:
        return None

    # Sort by modification time, most recent first
    latest_file = max(transcript_files, key=os.path.getmtime)
    return latest_file


def save_analysis(analysis_text, transcript_file):
    """Save analysis results to a structured output file.

    Creates a timestamped file containing the action items analysis
    with metadata about source and analysis parameters.

    Args:
        analysis_text (str): Action items analysis from Gemini
        transcript_file (str): Source transcript file path

    Returns:
        str: Path to the created output file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = Path(transcript_file).stem
    output_file = f"action_items_{base_name}_{timestamp}.txt"

    # Create a structured output
    content = f"""Action Items Analysis
Source: {transcript_file}
Analyzed: {datetime.now().isoformat()}
Model: {MODEL_NAME}

Action Items:
{analysis_text}
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Action items saved to: {output_file}")
    return output_file


def display_analysis(analysis_text):
    """Display action items analysis in a formatted console output.

    Args:
        analysis_text (str): Action items text from analysis
    """
    print("\n" + "=" * 50)
    print("ACTION ITEMS")
    print("=" * 50)

    if analysis_text.strip().lower() == "none":
        print("No clear action items found")
    else:
        print(analysis_text)

    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze conversation transcripts for action items"
    )
    parser.add_argument("transcript", nargs="?", help="Path to transcript JSON file")
    parser.add_argument(
        "--latest", action="store_true", help="Analyze the most recent transcript"
    )
    parser.add_argument("--save", action="store_true", help="Save analysis to file")
    parser.add_argument("--output", help="Custom output file name")

    args = parser.parse_args()

    # Determine which transcript to analyze
    if args.latest:
        transcript_file = find_latest_transcript()
        if not transcript_file:
            print("Error: No transcript files found in current directory")
            return
        print(f"Analyzing latest transcript: {transcript_file}")
    elif args.transcript:
        transcript_file = args.transcript
        if not os.path.exists(transcript_file):
            print(f"Error: Transcript file not found: {transcript_file}")
            return
    else:
        print("Error: Please specify a transcript file or use --latest")
        return

    # Load and process transcript
    print(f"Loading transcript: {transcript_file}")
    transcript_data = load_transcript(transcript_file)
    if not transcript_data:
        return

    # Extract conversation text
    conversation_text = extract_conversation_text(transcript_data)
    if not conversation_text.strip():
        print("Error: No conversation content found in transcript")
        return

    print(f"Found conversation with {len(conversation_text.split())} words")
    print("Analyzing conversation with Gemini Flash...")

    # Analyze with Gemini
    analysis = analyze_conversation(conversation_text)
    if not analysis:
        print("Error: Failed to analyze conversation")
        return

    # Display results
    display_analysis(analysis)

    # Save if requested
    if args.save or args.output:
        if args.output:
            # Custom output file
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(analysis)
            print(f"Analysis saved to: {args.output}")
        else:
            # Auto-generated filename
            save_analysis(analysis, transcript_file)


if __name__ == "__main__":
    main()
