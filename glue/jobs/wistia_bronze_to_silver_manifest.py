
import json
import sys

import boto3

from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

args = getResolvedOptions(
    sys.argv,
    ["BUCKET", "START_DATE", "END_DATE", "MANIFEST_KEY"]
)

bucket = args["BUCKET"]
start_date = args["START_DATE"]
end_date = args["END_DATE"]
manifest_key = args["MANIFEST_KEY"]

spark = SparkSession.builder.appName(
    "WistiaBronzeToSilverEvents"
).getOrCreate()


# Load the completion manifest.
s3 = boto3.client("s3")

expected_prefix = (
    "bronze/manifests/viewing_events/"
    f"start_date={start_date}/"
    f"end_date={end_date}/"
)

if not manifest_key.startswith(expected_prefix):
    raise ValueError("Manifest key does not match the requested dates.")

manifest_response = s3.get_object(
    Bucket=bucket,
    Key=manifest_key,
)

manifest = json.loads(
    manifest_response["Body"].read().decode("utf-8")
)

if manifest.get("status") != "SUCCEEDED":
    raise ValueError("Manifest does not indicate a successful ingestion.")

if manifest.get("dataset") != "viewing_events":
    raise ValueError("Unexpected manifest dataset.")

if (
    manifest.get("start_date") != start_date
    or manifest.get("end_date") != end_date
):
    raise ValueError("Manifest date range does not match job arguments.")

run_id = manifest.get("run_id")
media_results = manifest.get("media_results", [])

if not isinstance(run_id, str) or not run_id:
    raise ValueError("Manifest is missing a valid run ID.")

if not media_results or any(
    item.get("complete") is not True for item in media_results
):
    raise ValueError("Manifest contains incomplete media ingestion.")

# Select only the media directories for this successful run.
bronze_paths = [
    (
        f"s3://{bucket}/bronze/viewing_events/"
        f"start_date={start_date}/"
        f"end_date={end_date}/"
        f"media_id={item['media_id']}/"
        f"run_id={run_id}/"
    )
    for item in media_results
    if item["total_events"] > 0
]

# Keep test output separate from the existing Silver dataset.
silver_path = (
    f"s3://{bucket}/silver_test/viewing_events/"
    f"start_date={start_date}/"
    f"end_date={end_date}/"
    f"run_id={run_id}/"
)

print(f"Validated manifest: s3://{bucket}/{manifest_key}")
print(f"Reading Bronze paths: {bronze_paths}")
print(f"Writing test Silver: {silver_path}")


# Read JSON documents using one document per file.

raw = (
    spark.read
    .option("multiLine", "true")
    .option("recursiveFileLookup", "true")
    .json(bronze_paths)
)


# Expand the array of events in each Bronze document.
events = raw.select(
    F.explode("data").alias("event"),
    F.col("_metadata.ingestion_timestamp")
        .alias("raw_ingestion_timestamp"),
    F.col("_metadata.run_id").alias("run_id")
)

silver = events.select(
    F.col("event.event_key").cast("string")
        .alias("event_key"),
    F.col("event.media_id").cast("string")
        .alias("media_id"),
    F.col("event.visitor_key").cast("string")
        .alias("visitor_key"),
    F.to_timestamp("event.received_at")
        .alias("event_timestamp"),
    F.col("event.percent_viewed").cast("double")
        .alias("percent_viewed"),
    F.col("event.country").cast("string")
        .alias("country"),
    F.col("event.region").cast("string")
        .alias("region"),
    F.col("event.city").cast("string")
        .alias("city"),
    F.col("event.conversion_type").cast("string")
        .alias("conversion_type"),
    F.col("event.media_name").cast("string")
        .alias("media_name"),
    F.to_timestamp("raw_ingestion_timestamp")
        .alias("ingestion_timestamp"),
    F.col("run_id")
)

silver = silver.withColumn(
    "event_date",
    F.to_date("event_timestamp")
)

# Data quality checks.
silver = silver.filter(
    F.col("event_key").isNotNull()
    & (F.length(F.trim("event_key")) > 0)
    & F.col("media_id").isNotNull()
    & F.col("event_timestamp").isNotNull()
    & F.col("percent_viewed").between(0.0, 1.0)
)

# Keep the most recently ingested copy of each event.
window = Window.partitionBy("event_key").orderBy(
    F.col("ingestion_timestamp").desc_nulls_last(),
    F.col("run_id").desc()
)

silver = (
    silver.withColumn(
        "_row_number",
        F.row_number().over(window)
    )
    .filter(F.col("_row_number") == 1)
    .drop("_row_number")
)

# Cache because we count and then write the same dataset.
silver = silver.cache()

record_count = silver.count()
print(f"Validated Silver records: {record_count}")

if record_count == 0:
    raise ValueError(
        "No valid viewing events found. "
        "Silver output was not overwritten."
    )

# This is a historical-window rebuild.
# Rerunning the job replaces this window's output.
(
    silver.coalesce(1)
    .write
    .mode("overwrite")
    .parquet(silver_path)
)

print(f"Silver output written to: {silver_path}")

silver.unpersist()
spark.stop()
