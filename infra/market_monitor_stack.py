from aws_cdk import Duration, Stack, aws_ec2, aws_events, aws_events_targets, aws_lambda, aws_rds, aws_s3, aws_ssm
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
        vpc = aws_ec2.Vpc(self, "MarketVpc", max_azs=2, nat_gateways=0)
        database = aws_rds.DatabaseInstance(
            self, "MarketDatabase", engine=aws_rds.DatabaseInstanceEngine.postgres(version=aws_rds.PostgresEngineVersion.VER_16),
            vpc=vpc, instance_type=aws_ec2.InstanceType.of(aws_ec2.InstanceClass.T4G, aws_ec2.InstanceSize.MICRO),
            allocated_storage=20, credentials=aws_rds.Credentials.from_generated_secret("market_monitor"),
            publicly_accessible=False, backup_retention=Duration.days(1), deletion_protection=False,
            vpc_subnets=aws_ec2.SubnetSelection(subnet_type=aws_ec2.SubnetType.PRIVATE_ISOLATED),
        )
        fred_key = aws_ssm.StringParameter.from_secure_string_parameter_attributes(
            self, "FredApiKey", parameter_name="/market-monitor/fred-api-key"
        )
        finnhub_key = aws_ssm.StringParameter.from_secure_string_parameter_attributes(
            self, "FinnhubApiKey", parameter_name="/market-monitor/finnhub-api-key"
        )
        ingestion = aws_lambda.DockerImageFunction(
            self,
            "DailyIngestion",
            code=aws_lambda.DockerImageCode.from_image_asset("../backend"),
            timeout=Duration.minutes(15),
            vpc=vpc,
            vpc_subnets=aws_ec2.SubnetSelection(subnet_type=aws_ec2.SubnetType.PRIVATE_ISOLATED),
            environment={
                "RAW_DATA_BUCKET": raw_data.bucket_name,
                "DATABASE_SECRET_ARN": database.secret.secret_arn,
                "FRED_PARAMETER_NAME": fred_key.parameter_name,
                "FINNHUB_PARAMETER_NAME": finnhub_key.parameter_name,
            },
        )
        raw_data.grant_put(ingestion)
        database.secret.grant_read(ingestion)
        fred_key.grant_read(ingestion)
        finnhub_key.grant_read(ingestion)
        database.connections.allow_default_port_from(ingestion)
        aws_events.Rule(
            self,
            "DailySchedule",
            schedule=aws_events.Schedule.cron(minute="15", hour="22", week_day="MON-FRI"),
            targets=[aws_events_targets.LambdaFunction(ingestion)],
        )
