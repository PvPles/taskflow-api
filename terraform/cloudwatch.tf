# The API's structured JSON log lines land here via Docker's awslogs driver.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/taskflow/api"
  retention_in_days = 14
}
