import json
import os

import boto3
from botocore.exceptions import ClientError

from wistia_schedule_dates import get_processing_dates


STATE_MACHINE_ARN = os.environ.get(
    "STATE_MACHINE_ARN",
    "arn:aws:states:us-east-1:214118274300:"
    "stateMachine:wistia-video-analytics-dev",
)

SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")


def lambda_handler(event, context):
    dates = get_processing_dates()
    processing_date = dates["start_date"]
    execution_name = f"wistia-daily-{processing_date}"

    execution_arn = STATE_MACHINE_ARN.replace(
        ":stateMachine:", ":execution:", 1
    ) + f":{execution_name}"

    sfn = boto3.client("stepfunctions")

    try:
        response = sfn.describe_execution(
            executionArn=execution_arn
        )

    except ClientError as error:
        error_code = error.response["Error"]["Code"]

        if error_code != "ExecutionDoesNotExist":
            raise

        if not SNS_TOPIC_ARN:
            raise ValueError(
                "SNS_TOPIC_ARN must be configured."
            )

        message = (
            "WISTIA DAILY PIPELINE MISSED RUN\n\n"
            f"Processing date: {processing_date}\n"
            f"Expected execution: {execution_name}\n"
            f"Execution ARN: {execution_arn}\n\n"
            "The expected Step Functions execution "
            "was not found during the watchdog check."
        )

        sns = boto3.client("sns")
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="ALERT: Wistia Daily Pipeline Missed Run",
            Message=message,
        )

        result = {
            "status": "MISSING",
            "processing_date": processing_date,
            "execution_name": execution_name,
            "alert_sent": True,
        }

        print(json.dumps(result))
        return result

    result = {
        "status": "FOUND",
        "processing_date": processing_date,
        "execution_name": execution_name,
        "execution_status": response["status"],
        "alert_sent": False,
    }

    print(json.dumps(result))
    return result
