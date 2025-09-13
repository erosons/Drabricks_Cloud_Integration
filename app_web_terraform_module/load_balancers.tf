# Keep exactly one subnet per AZ
data "aws_subnet" "public_each" {
  for_each = toset(local.all_subnet_ids)
  id       = each.value
}



resource "aws_lb" "web_app_lb" {
  name               = "${var.app_name}-${var.environment_name}-lb"
  internal           = false
  load_balancer_type = "application"

  # pass IDs
  security_groups = [aws_security_group.default.id]
  subnets        =  local.alb_subnets   # one per AZ # <- use .ids (no for-comprehension)

  enable_deletion_protection = false
  

  tags = {
    Name = "web-app-lb"
  }
}


resource "aws_lb_listener" "web_app_tg" {
  load_balancer_arn = aws_lb.web_app_lb.arn
  port     = 8080
  protocol = "HTTP"

   default_action {
    type = "fixed-response"
      fixed_response {
        content_type = "text/plain"
        message_body = "404: page not found"
        status_code  = "404"
        }
   }

  tags = var.tags
}

resource "aws_lb_target_group" "web_app_tg" {
  name     = "${var.app_name}-${var.environment_name}-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = data.aws_vpc.default.id

  health_check {
    path                = "/"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 5
    unhealthy_threshold = 2
    matcher             = "200-399"
  }

  tags = {
    Name = "web-app-tg"
  }
}

resource "aws_lb_listener_rule" "web_app_listener_rule" {
  listener_arn = aws_lb_listener.web_app_tg.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web_app_tg.arn
  }

  condition {
    path_pattern {
      values = ["*"]
    }
  }
}


resource "aws_lb_target_group_attachment" "web_app_tg_attachment" {
  target_group_arn = aws_lb_target_group.web_app_tg.arn
  target_id        = aws_instance.instance_1.id
  port             = 8080
}

resource "aws_lb_target_group_attachment" "web_app_tg_attachment2" {
  target_group_arn = aws_lb_target_group.web_app_tg.arn
  target_id        = aws_instance.instance_2.id
  port             = 8080
}

