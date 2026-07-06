data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Secrets are generated here and land only in the instance's user_data and
# Terraform state - never in the repo. (For a bigger system: Secrets Manager.)
resource "random_password" "jwt_secret" {
  length  = 48
  special = false
}

resource "random_password" "db_password" {
  length  = 24
  special = false
}

resource "aws_instance" "api" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.app.id]
  iam_instance_profile        = aws_iam_instance_profile.api.name
  key_name                    = var.ssh_key_name != "" ? var.ssh_key_name : null
  associate_public_ip_address = true

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    app_image   = var.app_image
    jwt_secret  = random_password.jwt_secret.result
    db_password = random_password.db_password.result
    aws_region  = var.aws_region
    log_group   = aws_cloudwatch_log_group.api.name
  })
  user_data_replace_on_change = true

  root_block_device {
    volume_size = 16
    volume_type = "gp3"
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  tags = { Name = "taskflow-api" }
}
