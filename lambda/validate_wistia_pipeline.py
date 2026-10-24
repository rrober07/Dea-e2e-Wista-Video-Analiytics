import boto3

s3 = boto3.client("s3")

DATASETS = [
    "silver_test/viewing_events",
    "gold_test/video_performance",
    "gold_test/daily_video_performance",
    "gold_test/geographic_performance",
]


def lambda_handler(event, context):
    bucket = event["bucket"]
    start_date = event["start_date"]
    end_date = event["end_date"]
    run_id = event["run_id"]

    partition = (
        f"start_date={start_date}/"
        f"end_date={end_date}/"
        f"run_id={run_id}/"
    )

    results = []

    for dataset in DATASETS:
        prefix = f"{dataset}/{partition}"

        paginator = s3.get_paginator("list_objects_v2")
        files = []

        for page in paginator.paginate(
            Bucket=bucket,
            Prefix=prefix
        ):
            for obj in page.get("Contents", []):
                if (
                    obj["Key"].endswith(".parquet")
                    and obj["Size"] > 0
                ):
                    files.append(obj["Key"])

        if not files:
            raise ValueError(
                f"Missing Parquet output: s3://{bucket}/{prefix}"
            )

        results.append({
            "dataset": dataset,
            "file_count": len(files),
            "status": "PASS"
        })

    return {
        "status": "SUCCEEDED",
        "run_id": run_id,
        "datasets_checked": len(results),
        "results": results
    }
