
import json
import boto3
import requests

SECRET_ID = "wistia/dev/api-token"
MEDIA_IDS = ["8hunphufxp", "9k4tbcdfg0"]

session = boto3.Session(
    profile_name="wistia-dev",
    region_name="us-east-1"
)

secrets_client = session.client("secretsmanager")

secret_response = secrets_client.get_secret_value(
    SecretId=SECRET_ID
)

secret = json.loads(secret_response["SecretString"])
api_token = secret["WISTIA_API_TOKEN"]

headers = {
    "Authorization": f"Bearer {api_token}",
    "Accept": "application/json"
}

for media_id in MEDIA_IDS:
    url = (
        "https://api.wistia.com/v1/stats/medias/"
        f"{media_id}.json"
    )

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        print(f"\nMedia ID: {media_id}")
        print(f"HTTP Status: {response.status_code}")

        if response.ok:
            data = response.json()
            print("Wistia authentication successful.")
            print("Response type:", type(data).__name__)

            if isinstance(data, dict):
                print("Available fields:", list(data.keys()))

        elif response.status_code == 401:
            print("Authentication failed. Check token.")

        elif response.status_code == 403:
            print("Token lacks required permissions.")

        elif response.status_code == 404:
            print("Media ID or endpoint not found.")

        else:
            print("API request failed.")

    except requests.RequestException as error:
        print("Connection error:", type(error).__name__)
