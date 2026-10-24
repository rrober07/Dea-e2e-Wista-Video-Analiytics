import json
import os

import boto3
from botocore.exceptions import ClientError

from wistia_schedule_dates import get_processing_dates


STATE_MACHINE_ARN = os.environ.get(
    "STATE_MACHINE_ARN",
    "arn:aws:states:us-east-1:214118274300:"
    "stateMachine:wistia-video-analytics-dev"
)


def lambda_handler(event, context):
    dates = get_processing_dates()

    execution_name = (
        f"wistia-daily-{dates['start_date']}"
    )

    client = boto3.client("stepfunctions")

    try:
        response = client.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=execution_name,
            input=json.dumps(dates, sort_keys=True)
        )

        result = {
            "status": "STARTED",
            "execution_name": execution_name,
            "execution_arn": response["executionArn"],
            "start_date": dates["start_date"],
            "end_date": dates["end_date"]
        }

    except ClientError as error:
        error_code = error.response["Error"]["Code"]

        if error_code != "ExecutionAlreadyExists":
            raise

        result = {
            "status": "ALREADY_STARTED",
            "execution_name": execution_name,
            "start_date": dates["start_date"],
            "end_date": dates["end_date"]
        }

    print(json.dumps(result))

    return result