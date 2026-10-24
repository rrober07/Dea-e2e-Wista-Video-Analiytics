
import json
import boto3

session = boto3.Session(
    profile_name="wistia-dev",
    region_name="us-east-1"
)

client = session.client("secretsmanager")

response = client.get_secret_value(
    SecretId="wistia/dev/api-token"
)

secret = json.loads(response["SecretString"])
api_token = secret["WISTIA_API_TOKEN"]

print("Successfully retrieved Wistia API token.")
print("Token present:", bool(api_token))
