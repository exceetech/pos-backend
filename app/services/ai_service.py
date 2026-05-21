import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("Missing GROQ_API_KEY environment variable")

client = Groq(
    api_key=GROQ_API_KEY
)


def generate_ai_insights(report_data):

    prompt = f"""
You are a senior retail growth analyst inside a modern POS system.

Your reader is a busy shop owner.
They do not want theory.
They want a simple daily action brief that explains what happened, what matters, and what to do next.

Style rules:
- Plain text only
- No code
- No JSON
- No markdown tables
- No emojis or icons
- Use Rs. for money, never use the rupee symbol
- Keep every line short and clear
- Prefer practical advice over generic comments
- Use product names from the data whenever possible
- If a value is missing, do not invent it
- Price and sales values are in INR

Sales Data:
{report_data}

Return the response EXACTLY in this structure:

STORE PULSE
One short line explaining today's overall business condition.
One short line showing the biggest opportunity or risk.

WHAT IS WORKING
Product name - why it is moving well.
Product name - what action to take next.

WHAT NEEDS ATTENTION
Product name - why it may be slow or risky.
Product name - what to change.

STOCK MOVES
Product name - restock, hold, or reduce.
Product name - suggested stock action.

PROFIT MOVES
One pricing, margin, upsell, or bundle idea.
One practical way to increase average bill value.

CUSTOMER SIGNALS
One line about buying pattern.
One line about what customers may prefer now.

NEXT BEST ACTIONS
Action 1 - immediate action for tomorrow.
Action 2 - stock, pricing, or promotion action.
Action 3 - simple experiment to try.

IMPORTANT:
- Each section must have 1 to 3 short lines only
- Avoid repeating the same idea in different sections
- Do not say "insufficient data" unless the data is truly empty
- If sales are weak, be direct but helpful
- If a product is strong, suggest how to use that strength
- Make the report feel fresh, modern, and useful
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional retail business analyst. Write concise, useful, emoji-free business insights for small shop owners. Use Rs. for currency."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.45,
            max_tokens=900
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI Service Error: {str(e)}")
        return "Intelligence report is currently recalibrating. Please check back in a few moments. System is processing high sales volume."
