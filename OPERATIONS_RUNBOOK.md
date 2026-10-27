# Wistia Video Analytics — Operations Runbook

**Environment:** `dev`  
**Region:** `us-east-1`  
**Time zone:** `America/Chicago`  
**Last successful scheduled verification:** October 26, 2026

## Daily schedule and expected behavior

| Time (Central) | Process | Expected behavior |
|---|---|---|
| 03:00 | `wistia-video-analytics-daily-dev` | Invokes `wistia-pipeline-scheduler-dev` to start the previous day's state machine execution |
| 04:00 | `wistia-pipeline-watchdog-daily-dev` | Invokes `wistia-pipeline-watchdog-dev` to check that the expected execution exists |

Daily execution name: `wistia-daily-YYYY-MM-DD`, where the date is the **previous Central calendar day**. A successful run may take the `NO_DATA` branch; that is not equivalent to a full data refresh.

## Daily verification (5–10 minutes)

### 1. Confirm Step Functions

Open [Step Functions](https://console.aws.amazon.com/states/home?region=us-east-1#/statemachines) and select `wistia-video-analytics-dev`.

- Find the execution named for yesterday's Central date.
- Confirm `SUCCEEDED` and note its start/end time.
- **Open the execution graph** and record whether it followed `NO_DATA` or ran Silver, Gold, and data-quality processing.
- If it failed, inspect the failing state and execution history before retrying.

### 2. Confirm watchdog Lambda

Open [CloudWatch Log Groups](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups) and navigate to `/aws/lambda/wistia-pipeline-watchdog-dev`.

- Open the newest log stream near 04:00 Central / 09:00 UTC during daylight saving time (10:00 UTC during standard time).
- Expect `status: FOUND`, the previous Central processing date, `execution_status: SUCCEEDED` for a healthy run, and `alert_sent: false`.
- Confirm the stream has `START`, `END`, and `REPORT` events without a runtime exception.

**Interpretation:** `FOUND` means the named execution exists; it does not necessarily mean the execution succeeded. Check `execution_status` separately.

### 3. Check alarms

Open [CloudWatch Alarms](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#alarmsV2:).

Review:

- `wistia-pipeline-execution-failed-dev`
- `wistia-pipeline-execution-timeout-dev`
- `wistia-pipeline-execution-aborted-dev`
- `wistia-pipeline-watchdog-errors-dev`

Confirm no unexpected `ALARM` state and that actions remain enabled. `Insufficient data` on a sparse Lambda error metric does not itself indicate a failed invocation; inspect actual logs and the missing-data policy.

### 4. Validate data freshness when events exist

If the state machine took the full processing branch, inspect the S3 manifest and outputs, Glue job results, data-quality Lambda result, Athena Gold-table row counts, and Streamlit dashboard freshness. Record counts and timestamps. **Do not infer successful analytics refresh from a Step Functions `SUCCEEDED` status alone.**

## Troubleshooting matrix

| Symptom | Likely area | First actions |
|---|---|---|
| No daily execution at 03:00 | EventBridge Scheduler, scheduler Lambda, IAM | Check schedule `Enabled`, timezone, target, scheduler Lambda logs, and invocation permissions |
| Execution `FAILED` | State machine task or permissions | Open execution history; identify failing state; inspect Lambda/Glue logs and relevant IAM errors |
| Execution `SUCCEEDED` in seconds | Possible `NO_DATA` path | Inspect state graph and ingestion manifest before treating as a problem |
| Watchdog reports `MISSING` | Daily scheduler/execution | Check whether expected execution name exists; investigate schedule and Lambda logs; validate processing date |
| Watchdog logs `FOUND` but status is `FAILED` | Pipeline failure | Investigate state machine execution and CloudWatch alarm; note watchdog itself only alerts on absence |
| No watchdog log stream at 04:00 | Watchdog schedule/invocation failure | Check schedule state, target, scheduler role and Lambda permissions; review EventBridge delivery evidence |
| Watchdog Lambda `Errors` alarm | Watchdog code, IAM, AWS API | Inspect latest watchdog log stream and stack trace; verify Step Functions `DescribeExecution` and SNS `Publish` permissions |
| No SNS email | Subscription or SNS policy/delivery | Check SNS subscription confirmed, topic ARN, alarm action and SNS delivery logs where available |
| GitHub deployment fails | OIDC trust, IAM policy, ZIP build, Lambda update | Inspect workflow step logs; verify role trust, target resource ARN, and deployment confirmation |

## Safe retry and change controls

- **Before retrying a failed execution**, inspect its history and determine whether a partial output or side effect exists.
- Do not reuse the same Step Functions execution name blindly; the scheduler intentionally treats duplicates as `ALREADY_STARTED`.
- Do not manually create a daily execution with a different name merely to satisfy the watchdog without investigating the root cause.
- Use GitHub Actions `verify-only` before a code deployment when validating AWS access.
- For authorized deployment, choose the target (`ingestion`, `scheduler`, or `watchdog`) and enter `DEPLOY` exactly.
- Verify the Lambda update status and run a controlled post-deployment test.
- Changes to Lambda handlers, environment variables, IAM roles, EventBridge schedules, and alarm settings are **not** part of the current code-only GitHub deployment workflow.

## Monitoring inventory

**SNS topic:** `arn:aws:sns:us-east-1:214118274300:wistia-video-analytics-dev-alerts`

**CloudWatch log retention:** 30 days for ingestion, scheduler, data-quality validator, and watchdog Lambda log groups.

**Known blind spot:** The watchdog's missing-execution notification requires the watchdog itself to run. A missed watchdog invocation is not reliably detected by its Lambda `Errors` alarm alone. Add an independent heartbeat / Scheduler delivery-failure alert for stronger operational coverage.

## October 26, 2026 verification record

- `wistia-daily-2026-10-25`: started at **03:00:47 Central**, finished at **03:00:50**, status **SUCCEEDED**.
- Watchdog invoked near **04:00 Central**; log stream's last event was **09:00:21 UTC**.
- Watchdog returned `FOUND`, processing date `2026-10-25`, execution status `SUCCEEDED`, `alert_sent: false`.
- Three Step Functions alarms displayed `OK`; watchdog error alarm displayed `Insufficient data`, with no active alarms in the observed overview.
- Four log groups displayed `1 month` retention.
- The daily execution graph, Gold-table freshness, and dashboard update were not inspected as part of this record.

## Change log template

| Date | Change | Commit / workflow | Verification | Operator |
|---|---|---|---|---|
| 2026-10-25 | Added watchdog source, tests, packaging, and GitHub deployment | `8a73c11` | 12 tests passed; GitHub deployment succeeded | Project maintainer |
| 2026-10-26 | Verified automated daily pipeline and watchdog | AWS Console and CloudWatch logs | Both scheduled processes completed as expected | Project maintainer |

## Escalation and incident record

For any operational failure, record the Central processing date, execution name/ARN, failure state, CloudWatch log stream, alarm state, alert delivery status, attempted remediation, and final verification. Keep credentials and sensitive payloads out of issue reports.
