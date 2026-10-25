import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "lambda"),
)

import check_wistia_daily_execution as watchdog


class TestWistiaWatchdog(unittest.TestCase):

    def setUp(self):
        self.dates = {
            "start_date": "2026-10-24",
            "end_date": "2026-10-24",
        }
        self.expected_name = "wistia-daily-2026-10-24"
        self.expected_arn = (
            "arn:aws:states:us-east-1:214118274300:"
            "execution:wistia-video-analytics-dev:"
            "wistia-daily-2026-10-24"
        )

    @patch.object(watchdog, "get_processing_dates")
    @patch.object(watchdog.boto3, "client")
    def test_execution_found(self, mock_client, mock_dates):
        mock_dates.return_value = self.dates

        sfn = MagicMock()
        sfn.describe_execution.return_value = {
            "status": "SUCCEEDED"
        }
        mock_client.return_value = sfn

        result = watchdog.lambda_handler({}, None)

        self.assertEqual(result["status"], "FOUND")
        self.assertFalse(result["alert_sent"])
        self.assertEqual(result["execution_status"], "SUCCEEDED")

        sfn.describe_execution.assert_called_once_with(
            executionArn=self.expected_arn
        )
        mock_client.assert_called_once_with("stepfunctions")

    @patch.object(watchdog, "SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:214118274300:test-alerts")
    @patch.object(watchdog, "get_processing_dates")
    @patch.object(watchdog.boto3, "client")
    def test_execution_missing(self, mock_client, mock_dates):
        mock_dates.return_value = self.dates

        sfn = MagicMock()
        sns = MagicMock()

        sfn.describe_execution.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ExecutionDoesNotExist",
                    "Message": "Execution not found",
                }
            },
            "DescribeExecution",
        )

        def client_factory(service):
            return {
                "stepfunctions": sfn,
                "sns": sns,
            }[service]

        mock_client.side_effect = client_factory

        result = watchdog.lambda_handler({}, None)

        self.assertEqual(result["status"], "MISSING")
        self.assertTrue(result["alert_sent"])
        sns.publish.assert_called_once()

        publish_args = sns.publish.call_args.kwargs
        self.assertIn(self.expected_name, publish_args["Message"])

    @patch.object(watchdog, "get_processing_dates")
    @patch.object(watchdog.boto3, "client")
    def test_unexpected_aws_error(self, mock_client, mock_dates):
        mock_dates.return_value = self.dates

        sfn = MagicMock()
        sfn.describe_execution.side_effect = ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "Access denied",
                }
            },
            "DescribeExecution",
        )
        mock_client.return_value = sfn

        with self.assertRaises(ClientError):
            watchdog.lambda_handler({}, None)

        mock_client.assert_called_once_with("stepfunctions")


if __name__ == "__main__":
    unittest.main()
