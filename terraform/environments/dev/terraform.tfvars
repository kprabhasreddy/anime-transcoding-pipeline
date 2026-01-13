# AWS Region - us-east-1 has best MediaConvert support
aws_region = "us-east-1"

# Environment name
environment = "dev"

# Path to Lambda packages (relative to terraform/environments/dev/)
lambda_zip_path = "../../../dist/lambda-deployment.zip"
layer_zip_path  = "../../../dist/lambda-layer.zip"

# Email for notifications 
notification_emails = ["prabhasreddy.kasireddy@wmich.edu"]

# Set to false for real transcoding, true for testing without AWS costs
mock_mode = false

# Feature flags
enable_h265 = true
enable_dash = true

