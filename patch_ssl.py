import re

with open("app/core/config.py", "r") as f:
    content = f.read()

patch = """import os
import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()

from dotenv import load_dotenv"""

content = content.replace("import os\nfrom dotenv import load_dotenv", patch)

with open("app/core/config.py", "w") as f:
    f.write(content)
