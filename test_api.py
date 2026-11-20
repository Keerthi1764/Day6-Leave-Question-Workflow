
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    print("Groq API key not found. Check your .env file.")
else:
    try:
        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
             model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": "Return valid JSON only. No markdown."
                },
                {
                    "role": "user",
                    "content": 'Return this JSON: {"answer":"Groq connection successful","source_section":"Test","confidence":1.0}'
                }
            ],
            response_format={"type": "json_object"}
        )

        print("Groq connection successful!")
        print("AI Response:")
        print(response.choices[0].message.content)

    except Exception as error:
        print("Groq connection failed.")
        print("Error:", error)
