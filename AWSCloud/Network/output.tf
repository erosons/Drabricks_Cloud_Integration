output "vpc_id"            { value = aws_vpc.this.id }
output "public_subnet_ids"  { value = [for s in aws_subnet.public  : s.id] }
output "private_subnet_ids" { value = [for s in aws_subnet.private : s.id] }
output "public_route_table" { value = aws_route_table.public.id }
output "private_route_tables" { value = [for rt in aws_route_table.private : rt.id] }
output "nat_gateway_id"     { value = aws_nat_gateway.this.id }
output "s3_gateway_endpoint_id" { value = aws_vpc_endpoint.s3.id }
