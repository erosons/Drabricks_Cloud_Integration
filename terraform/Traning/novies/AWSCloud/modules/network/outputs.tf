output "vpc_id"                 { value = aws_vpc.ws.id }
output "ws_private_subnet_id"   { value = aws_subnet.ws_private.id }
output "ws_pe_subnet_id"        { value = aws_subnet.ws_pe.id }
output "transit_vpc_id"         { value = aws_vpc.transit.id }
output "transit_pe_subnet_id"   { value = aws_subnet.transit_pe.id }
output "workspace_sg_id"        { value = aws_security_group.workspace.id }
output "backend_sg_id"          { value = aws_security_group.backend.id }
output "frontend_sg_id"         { value = aws_security_group.frontend.id }
