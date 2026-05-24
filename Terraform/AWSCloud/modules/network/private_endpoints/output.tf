output "backend_workspace_vpce_id" { value = aws_vpc_endpoint.backend_workspace.id }
output "backend_scc_vpce_id"       { value = aws_vpc_endpoint.backend_scc.id }
output "frontend_vpce_id"          { value = aws_vpc_endpoint.frontend.id }

# Handy IP of the front-end VPCE ENI to build A-record
output "frontend_vpce_ip" {
  value = try(aws_vpc_endpoint.frontend.dns_entry[0].ip_address, null)
}
