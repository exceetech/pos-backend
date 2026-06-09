import re

filepath = "/Users/adeebfarhan/.gemini/antigravity/brain/bfb1db26-2cee-4b41-a28b-ad6f4807923e/scratch/test_all_insights.py"
with open(filepath, "r") as f:
    content = f.read()

# Remove returns import
content = re.sub(r'from app\.models\.returns import ReturnInvoice\n', '', content)

# Change output logic to write to a markdown artifact
output_replacement = """
    insights = ins.generate_structured_insights(db, 1)
    
    report = f"# AI Insights Live Database Test Report\\n\\n"
    report += f"**Target Shop:** {shop.name} (ID: {shop.id})\\n"
    report += f"**Total Insights Triggered by Mock Data:** {len(insights)}\\n\\n"
    report += "---\\n\\n"
    
    if not insights:
        report += "No insights were triggered.\\n"
    else:
        for i, ins_dict in enumerate(insights):
            report += f"### {i+1}. [{ins_dict['type'].upper()}] {ins_dict['title']}\\n"
            report += f"> {ins_dict['description']}\\n\\n"
            report += f"**Action Required:** {ins_dict.get('actionText', 'None')} (`{ins_dict.get('actionType', 'NONE')}`)\\n\\n"
            report += "---\\n\\n"
            
    with open("/Users/adeebfarhan/.gemini/antigravity/brain/bfb1db26-2cee-4b41-a28b-ad6f4807923e/artifacts/ai_mock_data_test_report.md", "w") as f:
        f.write(report)
        
    print(f"Generated test report with {len(insights)} mock insights.")
"""

content = re.sub(r'    insights = ins\.generate_structured_insights\(1, db\).*', output_replacement, content, flags=re.DOTALL)

with open(filepath, "w") as f:
    f.write(content)
