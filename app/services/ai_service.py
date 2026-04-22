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
You are an expert RETAIL BUSINESS ANALYST working for an AI powered POS system.

Your task is to analyze sales data and generate PRACTICAL BUSINESS INSIGHTS that help a shop owner increase profit.

RULES:
- DO NOT generate code
- DO NOT generate programming explanations
- Only provide business insights
- Use SHORT lines
- Use the ICONS provided below
- Keep insights actionable and practical
- Price is in INR
- Return headings in red colour and underlined

Sales Data:
{report_data}

Analyze the data and provide insights for:

1️⃣ Best Selling Products  
2️⃣ Slow Selling Products  
3️⃣ Inventory Strategy  
4️⃣ Profit Strategy  
5️⃣ Sales Insights  
6️⃣ Stock Recommendation  
7️⃣ Marketing Ideas  

Return the response EXACTLY in this structure:

BEST SELLING PRODUCTS
🔥 product name — why it sells well
🔥 product name — reason

SLOW SELLING PRODUCTS
⚠️ product name — why it is slow

📦 INVENTORY STRATEGY
📦 Recommended stock levels for fast moving products
📦 How much inventory should be maintained

PROFIT STRATEGY
💰 Pricing improvements
💰 Upselling ideas
💰 Bundle suggestions

SALES INSIGHTS
📊 Patterns in sales behavior
📊 Customer buying trends

STOCK RECOMMENDATION
📦 Suggested stock levels for top products
📦 When to restock based on demand

MARKETING IDEAS
🚀 Promotion ideas
🚀 Cross selling opportunities
🚀 Discount strategies

IMPORTANT:
- Each point must be ONE SHORT line
- Maximum 2–3 lines per section
- Focus on practical business improvement
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are a professional retail business intelligence expert."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.3
    )

    return response.choices[0].message.content