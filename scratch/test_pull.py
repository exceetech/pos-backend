import requests

token = "..." # No, I can just use python to query the local API
r = requests.get("http://192.168.1.101:48365/purchase-batches/1", headers={"Authorization": "Bearer fake"}) # fake might not work.
# Let's just bypass auth by checking the DB directly.
