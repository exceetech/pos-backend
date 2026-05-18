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
- DO NOT generate code or JSON
- Only provide business insights in plain text
- DO NOT use emojis or icons
- Use the 'Rs.' prefix for all currency values (e.g. Rs. 500)
- Use SHORT lines
- Keep insights actionable and practical
- Price is in INR

Sales Data:
{report_data}

Analyze the data and provide insights for:

1. Best Selling Products  
2. Slow Selling Products  
3. Inventory Strategy  
4. Profit Strategy  
5. Sales Insights  
6. Stock Recommendation  
7. Marketing Ideas  

Return the response EXACTLY in this structure:

BEST SELLING PRODUCTS
Product name — why it sells well
Product name — reason

SLOW SELLING PRODUCTS
Product name — why it is slow

INVENTORY STRATEGY
Recommended stock levels for fast moving products
How much inventory should be maintained

PROFIT STRATEGY
Pricing improvements
Upselling ideas
Bundle suggestions

SALES INSIGHTS
Patterns in sales behavior
Customer buying trends

STOCK RECOMMENDATION
Suggested stock levels for top products
When to restock based on demand

MARKETING IDEAS
Promotion ideas
Cross selling opportunities
Discount strategies

IMPORTANT:
- Each point must be ONE SHORT line
- Maximum 2–3 lines per section
- DO NOT use the Rupee symbol (₹), use 'Rs.' instead.
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional retail business intelligence expert who provides clean, emoji-free insights using Rs. for currency."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI Service Error: {str(e)}")
        return "Intelligence report is currently recalibrating. Please check back in a few moments. System is processing high sales volume."