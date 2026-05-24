# Unique suffix for names
resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

resource "time_sleep" "wait_for_workspace" {
  create_duration = "45s"
}
