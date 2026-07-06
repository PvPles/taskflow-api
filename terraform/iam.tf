# Instance role: just enough for the Docker awslogs driver to ship logs.
resource "aws_iam_role" "api" {
  name_prefix = "taskflow-api-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "logs" {
  name_prefix = "cloudwatch-logs-"
  role        = aws_iam_role.api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams",
      ]
      Resource = "${aws_cloudwatch_log_group.api.arn}:*"
    }]
  })
}

resource "aws_iam_instance_profile" "api" {
  name_prefix = "taskflow-api-"
  role        = aws_iam_role.api.name
}
