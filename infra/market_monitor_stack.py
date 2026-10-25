from aws_cdk import Duration, Stack, aws_events, aws_events_targets, aws_iam, aws_lambda, aws_s3
from constructs import Construct


class MarketMonitorStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        raw_data = aws_s3.Bucket(
            self,
            "RawMarketData",
            encryption=aws_s3.BucketEncryption.S3_MANAGED,
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            auto_delete_objects=False,
        )
        ingestion = aws_lambda.Function(
            self,
            "DailyIngestion",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            handler="handler.main",
            code=aws_lambda.Code.from_asset("../backend"),
            timeout=Duration.minutes(15),
            environment={"RAW_DATA_BUCKET": raw_data.bucket_name},
        )
        raw_data.grant_put(ingestion)
        ingestion.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=["ssm:GetParameter", "secretsmanager:GetSecretValue"],
                resources=["*"],
            )
        )
        aws_events.Rule(
            self,
            "DailySchedule",
            schedule=aws_events.Schedule.cron(minute="15", hour="22", week_day="MON-FRI"),
            targets=[aws_events_targets.LambdaFunction(ingestion)],
        )
