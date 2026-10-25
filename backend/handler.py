"""AWS Lambda entry point for scheduled ingestion."""
from app.ingestion.service import run_ingestion


def main(event, context):
    run_ingestion()
    return {"statusCode": 200, "body": "Market data ingestion completed"}
