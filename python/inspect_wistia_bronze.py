
import json
import boto3

AWS_PROFILE = "wistia-dev"
AWS_REGION = "us-east-1"
BUCKET = "wistia-video-analytics-dev"

PREFIX = (
    "bronze/viewing_events/"
    "start_date=2026-04-08/"
    "end_date=2026-04-14/"
)

session = boto3.Session(
    profile_name=AWS_PROFILE,
    region_name=AWS_REGION
)
s3 = session.client("s3")

objects = s3.list_objects_v2(
    Bucket=BUCKET,
    Prefix=PREFIX
).get("Contents", [])

for obj in objects:
    key = obj["Key"]

    if not key.endswith(".json"):
        continue

    response = s3.get_object(
        Bucket=BUCKET,
        Key=key
    )

    document = json.loads(
        response["Body"].read()
    )

    records = document["data"]
    metadata = document["_metadata"]

    print("\n" + "=" * 65)
    print("Media ID:", metadata["media_id"])
    print("Record count:", len(records))
    print("S3 key:", key)

    if records:
        print("Event fields:", list(records[0].keys()))

        for field, value in records[0].items():
            print(
                f"  {field}: {type(value).__name__}"
            )
