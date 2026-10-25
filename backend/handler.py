"""AWS Lambda entry point for scheduled ingestion."""
import json
import os

import boto3

from app.ingestion.service import run_ingestion


def configure_aws_runtime() -> None:
    ssm = boto3.client("ssm")
    secrets = boto3.client("secretsmanager")
    os.environ["FRED_API_KEY"] = ssm.get_parameter(
        Name=os.environ["FRED_PARAMETER_NAME"], WithDecryption=True
    )["Parameter"]["Value"]
    os.environ["FINNHUB_API_KEY"] = ssm.get_parameter(
        Name=os.environ["FINNHUB_PARAMETER_NAME"], WithDecryption=True
    )["Parameter"]["Value"]
    database = json.loads(
        secrets.get_secret_value(SecretId=os.environ["DATABASE_SECRET_ARN"])["SecretString"]
    )
    os.environ["DATABASE_URL"] = (
        f"postgresql+psycopg://{database['username']}:{database['password']}@"
        f"{database['host']}:{database['port']}/{database['dbname']}"
    )


def main(event, context):
    configure_aws_runtime()
    run_ingestion()
    return {"statusCode": 200, "body": "Market data ingestion completed"}
