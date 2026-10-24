
import sys

from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

args = getResolvedOptions(
    sys.argv,
    ["BUCKET", "START_DATE", "END_DATE"]
)

bucket = args["BUCKET"]
start_date = args["START_DATE"]
end_date = args["END_DATE"]

spark = SparkSession.builder.appName(
    "WistiaSilverToGold"
).getOrCreate()

silver_path = (
    f"s3://{bucket}/silver/viewing_events/"
    f"start_date={start_date}/end_date={end_date}/"
)

gold_base = (
    f"s3://{bucket}/gold/"
)

events = spark.read.parquet(silver_path)

# Validate source data
source_count = events.count()
print(f"Silver source records: {source_count}")

if source_count == 0:
    raise ValueError("No Silver records found")

# 1. Video performance
video_performance = (
    events.groupBy("media_id")
    .agg(
        F.max("media_name").alias("media_name"),
        F.count("*").alias("total_events"),
        F.countDistinct("visitor_key").alias("unique_visitors"),
        F.round(
            F.avg("percent_viewed") * 100, 2
        ).alias("avg_percent_viewed"),
        F.sum(
            F.when(
                F.col("percent_viewed") >= 0.90, 1
            ).otherwise(0)
        ).alias("near_complete_views")
    )
)

# 2. Daily video performance
daily_video_performance = (
    events.groupBy("event_date", "media_id")
    .agg(
        F.max("media_name").alias("media_name"),
        F.count("*").alias("total_events"),
        F.countDistinct("visitor_key").alias("unique_visitors"),
        F.round(
            F.avg("percent_viewed") * 100, 2
        ).alias("avg_percent_viewed")
    )
)

# 3. Geographic performance
geographic_performance = (
    events.groupBy("media_id", "country")
    .agg(
        F.max("media_name").alias("media_name"),
        F.count("*").alias("total_events"),
        F.countDistinct("visitor_key").alias("unique_visitors"),
        F.round(
            F.avg("percent_viewed") * 100, 2
        ).alias("avg_percent_viewed")
    )
)

datasets = {
    "video_performance": video_performance,
    "daily_video_performance": daily_video_performance,
    "geographic_performance": geographic_performance
}

for name, df in datasets.items():
    output_path = (
        f"{gold_base}{name}/"
        f"start_date={start_date}/"
        f"end_date={end_date}/"
    )

    row_count = df.count()

    print(f"Writing {name}: {row_count} rows")

    df.coalesce(1).write.mode("overwrite").parquet(
        output_path
    )

print("Wistia Silver-to-Gold job completed successfully")
