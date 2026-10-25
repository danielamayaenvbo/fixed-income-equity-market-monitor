#!/usr/bin/env python3
import aws_cdk as cdk

from market_monitor_stack import MarketMonitorStack

app = cdk.App()
MarketMonitorStack(app, "MarketMonitorStack")
app.synth()
