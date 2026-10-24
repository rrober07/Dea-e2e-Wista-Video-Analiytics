
import sys

from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

args = getResolvedOptions(
    sys.argv,
    ["BUCKET", "START_DATE", "END_DATE"]
)

bucket = args["BUCKET"]
start_date = args["START_DATE"]
end_date = args["END_DATE"]

spark = SparkSession.builder.appName(
    "WistiaBronzeToSilverEvents"
).getOrCreate()

bronze_path = (
    f"s3://{bucket}/bronze/viewing_events/"
    f"start_date={start_date}/"
    f"end_date={end_date}/"
)

silver_path = (
    f"s3://{bucket}/silver/viewing_events/"
    f"start_date={start_date}/"
    f"end_date={end_date}/"
)

print(f"Reading Bronze: {bronze_path}")

# Read JSON documents using one document per file.
raw = (
    spark.read
    .option("multiLine", "true")
    .option("recursiveFileLookup", "true")
    .json(bronze_path)
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
