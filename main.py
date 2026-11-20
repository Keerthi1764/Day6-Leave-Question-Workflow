
import csv
import os
import re
import json
import requests

from pathlib import Path
from dotenv import load_dotenv
from groq import Groq


# --------------------------------
# 1. CONFIGURATION
# --------------------------------

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not api_key:
    raise ValueError("GROQ_API_KEY not found in .env file")

client = Groq(api_key=api_key)


# --------------------------------
# 2. LOAD LEAVE POLICY
# --------------------------------

def load_policy():

    file_path = Path(__file__).parent / "Day6_Leave_Policy.txt"

    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


# --------------------------------
# 3. RETRIEVE POLICY SECTION
# --------------------------------

def retrieve_policy(question, policy):

    sections = re.split(
        r"(?m)(?=^\d+\.\s)",
        policy
    )

    sections = [
        section.strip()
        for section in sections
        if re.match(r"^\d+\.", section.strip())
    ]

    skip_words = {
        "the", "and", "for", "can", "what", "how",
        "who", "does", "will", "when", "with", "are",
        "you", "your", "have", "any", "get", "much",
        "many", "there", "this", "that", "from", "after",
        "my", "i", "is", "a", "an", "of", "to"
    }

    words = re.findall(r"[a-z]+", question.lower())

    keywords = [
        word for word in words
        if len(word) > 2 and word not in skip_words
    ]

    scored_sections = []

    topic_phrases = [
        "carry over",
        "unused leave",
        "half a day",
        "half-day",
        "casual leave",
        "sick leave",
        "backup approver",
        "manager"
    ]

    for section in sections:

        section_text = section.lower()
        score = 0

        for word in keywords:
            if re.search(
                r"\b" + re.escape(word) + r"\b",
                section_text
            ):
                score += 1

        for phrase in topic_phrases:
            if phrase in question.lower() and phrase in section_text:
                score += 3

        scored_sections.append((section, score))

    scored_sections.sort(
        key=lambda item: item[1],
        reverse=True
    )

    if not scored_sections or scored_sections[0][1] == 0:
        return None

    return scored_sections[0][0]


# --------------------------------
# 4. GENERATE AI JSON USING GROQ
# --------------------------------

def generate_ai_answer(question, retrieved_section):

    match = re.match(r"^(\d+)\.", retrieved_section)

    if not match:
        raise ValueError("Could not identify policy section number")

    section_number = match.group(1)

    prompt = f"""
You are an employee leave policy assistant.

Answer the employee question using ONLY the
retrieved leave policy section.

Employee question:
{question}

Retrieved policy section:
{retrieved_section}

Return JSON with exactly these three keys:

{{
    "answer": "Answer based only on the policy",
    "source_section": "Section {section_number}",
    "confidence": 0.95
}}

Rules:
1. Do not use outside information.
2. Do not invent policy details.
3. Use Section {section_number} as the source.
4. Confidence must be a number between 0 and 1.
5. Return JSON only. No markdown.
"""

    response = client.chat.completions.create(

        model="openai/gpt-oss-120b",

        messages=[
            {
                "role": "system",
                "content": "Return valid JSON only."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        response_format={"type": "json_object"}
    )

    return response.choices[0].message.content


# --------------------------------
# 5. VALIDATE JSON
# --------------------------------

def validate_json(ai_response, expected_section):

    data = json.loads(ai_response)

    required_keys = {
        "answer",
        "source_section",
        "confidence"
    }

    if not isinstance(data, dict):
        raise ValueError("Response must be a JSON object")

    if set(data.keys()) != required_keys:
        raise ValueError("JSON keys are missing or incorrect")

    if not isinstance(data["answer"], str) or not data["answer"].strip():
        raise ValueError("Answer must be non-empty text")

    if data["source_section"] != expected_section:
        raise ValueError("Incorrect source section")

    confidence = data["confidence"]

    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise ValueError("Invalid confidence value")

    return data


# --------------------------------
# 6. SEND DATA TO WEBHOOK
# --------------------------------

def send_to_webhook(data):

    if not WEBHOOK_URL:
        print("\nWebhook URL not configured.")
        return False

    try:

        response = requests.post(
            WEBHOOK_URL,
            json=data,
            timeout=15
        )

        response.raise_for_status()

        print("\nWebhook submission successful!")
        print("Status code:", response.status_code)

        return True

    except requests.RequestException as error:

        print("\nWebhook submission failed:")
        print(error)

        return False


# --------------------------------
# 7. SAVE TEST RESULTS TO CSV
# --------------------------------

def save_test_log(question, section, correct, approval, webhook_reached):

    file_path = Path(__file__).parent / "test_log.csv"

    file_exists = file_path.exists() and file_path.stat().st_size > 0

    with open(file_path, "a", newline="", encoding="utf-8") as file:

        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "Question",
                "Section Cited",
                "Correct",
                "Approval",
                "Webhook Reached"
            ])

        writer.writerow([
            question,
            section,
            correct,
            approval,
            webhook_reached
        ])

    print("\nTest result saved to test_log.csv!")


# --------------------------------
# 8. MAIN WORKFLOW
# --------------------------------

if __name__ == "__main__":

    policy = load_policy()

    question = input("\nEnter your leave question: ").strip()

    if not question:
        print("Please enter a question.")
        raise SystemExit(1)

    # Retrieve policy section
    retrieved_section = retrieve_policy(question, policy)

    print("\nRetrieved Policy Section:")
    print("------------------------")

    if retrieved_section is None:

        print("NO MATCHING SECTION")

        result = {
            "answer": "Not found in the leave policy",
            "source_section": "None",
            "confidence": 1.0
        }

        actual_section = "None"

    else:

        print(retrieved_section)

        try:

            ai_response = generate_ai_answer(
                question,
                retrieved_section
            )

            section_match = re.match(
                r"^(\d+)\.",
                retrieved_section
            )

            if not section_match:
                raise ValueError("Could not identify policy section")

            section_number = section_match.group(1)

            actual_section = f"Section {section_number}"

            result = validate_json(
                ai_response,
                actual_section
            )

        except Exception as error:

            print("\nAI or JSON validation failed:")
            print(error)

            print("Stopping workflow. Nothing sent.")

            raise SystemExit(1)

    # Display JSON
    print("\nAI Response (JSON):")
    print("-------------------")

    print(json.dumps(result, indent=4))

    # Expected sections for five test questions
    expected_sections = {
        "can i carry over unused leave?": "Section 7",
        "who approves my leave if my manager is on leave?": "Section 4",
        "can i take half a day of sick leave?": "Section 3",
        "how many days in advance must i apply for casual leave?": "Section 2",
        "what's the canteen menu today?": "None"
    }

    expected = expected_sections.get(question.lower())

    if expected is None:
        correct = "Not evaluated"
    else:
        correct = "Yes" if actual_section == expected else "No"

    # Human approval
    approval = input("\nApprove? (y/n): ").strip().lower()

    webhook_reached = "No"

    if approval == "y":

        print("\nHuman approval received!")

        if retrieved_section is None:

            print("Out-of-scope question. Nothing sent.")

        else:

            sent = send_to_webhook(result)

            if sent:
                webhook_reached = "Yes"

    else:

        print("\nRejected: nothing sent.")

    # Save result to CSV
    approval_status = "Approved" if approval == "y" else "Rejected"

    save_test_log(
        question,
        actual_section,
        correct,
        approval_status,
        webhook_reached
    )

