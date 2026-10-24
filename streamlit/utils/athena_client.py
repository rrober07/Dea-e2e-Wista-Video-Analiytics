
import time

import boto3
import pandas as pd


AWS_PROFILE = "wistia-dev"
AWS_REGION = "us-east-1"
ATHENA_WORKGROUP = "primary"
ATHENA_DATABASE = "wistia_analytics_gold_dev"
ATHENA_OUTPUT = (
    "s3://wistia-video-analytics-dev/athena-results/"
)


def get_athena_client():
    session = boto3.Session(
        profile_name=AWS_PROFILE,
        region_name=AWS_REGION,
    )
    return session.client("athena")


def run_athena_query(sql, timeout_seconds=120):
    client = get_athena_client()

    response = client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={
            "Database": ATHENA_DATABASE
        },
        ResultConfiguration={
            "OutputLocation": ATHENA_OUTPUT
        },
        WorkGroup=ATHENA_WORKGROUP,
    )

    query_id = response["QueryExecutionId"]
    start_time = time.monotonic()

    while True:
        execution = client.get_query_execution(
            QueryExecutionId=query_id
        )

        status = execution["QueryExecution"]["Status"]
        state = status["State"]

        if state == "SUCCEEDED":
            break

        if state in ("FAILED", "CANCELLED"):
            reason = status.get(
                "StateChangeReason", "Unknown reason"
            )
            raise RuntimeError(
                f"Athena query {state}: {reason}"
            )

        if time.monotonic() - start_time > timeout_seconds:
            raise TimeoutError(
                f"Athena query timed out: {query_id}"
            )

        time.sleep(2)

    paginator = client.get_paginator("get_query_results")

    rows = []
    columns = None

    for page in paginator.paginate(
        QueryExecutionId=query_id
    ):
        result_set = page["ResultSet"]

        if columns is None:
            columns = [
                col["Name"]
                for col in result_set["ResultSetMetadata"][
                    "ColumnInfo"
                ]
            ]

        for row in result_set["Rows"]:
            values = [
                cell.get("VarCharValue")
                for cell in row["Data"]
            ]
            rows.append(values)

    # Athena includes the column header as the first row.
    if rows:
        rows = rows[1:]

    return pd.DataFrame(rows, columns=columns)


if __name__ == "__main__":
    sql = """
        SELECT
            media_id,
            media_name,
            total_events,
            unique_visitors,
            avg_percent_viewed,
            near_complete_views
        FROM wistia_analytics_gold_dev.video_performance
        ORDER BY total_events DESC
    """

    df = run_athena_query(sql)
    print(df.to_string(index=False))
