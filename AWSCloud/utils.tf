# Unique suffix for names
resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}