import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "lambda"),
)

import start_wistia_pipeline


class TestWistiaPipelineScheduler(unittest.TestCase):

    def setUp(self):
        self.dates = {
            "start_date": "2026-10-24",
            "end_date": "2026-10-24",
        }

        self.client = MagicMock()

        self.date_patcher = patch.object(
            start_wistia_pipeline,
            "get_processing_dates",
            return_value=self.dates,
        )

        self.boto_patcher = patch.object(
            start_wistia_pipeline.boto3,
            "client",
            return_value=self.client,
        )

        self.date_patcher.start()
        self.boto_patcher.start()

        self.addCleanup(self.date_patcher.stop)
        self.addCleanup(self.boto_patcher.stop)

    def test_successful_execution(self):
        self.client.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test"
        }

        result = start_wistia_pipeline.lambda_handler({}, None)

        self.assertEqual(result["status"], "STARTED")
        self.assertEqual(
            result["execution_name"],
            "wistia-daily-2026-10-24",
        )
        self.assertIn("execution_arn", result)

        self.client.start_execution.assert_called_once_with(
            stateMachineArn=start_wistia_pipeline.STATE_MACHINE_ARN,
            name="wistia-daily-2026-10-24",
            input=json.dumps(self.dates, sort_keys=True),
        )

    def test_duplicate_execution(self):
        self.client.start_execution.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ExecutionAlreadyExists",
                    "Message": "Execution already exists",
                }
            },
            "StartExecution",
        )

        result = start_wistia_pipeline.lambda_handler({}, None)

        self.assertEqual(result["status"], "ALREADY_STARTED")
        self.assertEqual(
            result["execution_name"],
            "wistia-daily-2026-10-24",
        )
        self.assertNotIn("execution_arn", result)

    def test_unexpected_aws_error(self):
        self.client.start_execution.side_effect = ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "Access denied",
                }
            },
            "StartExecution",
        )

        with self.assertRaises(ClientError):
            start_wistia_pipeline.lambda_handler({}, None)


if __name__ == "__main__":
    unittest.main()
