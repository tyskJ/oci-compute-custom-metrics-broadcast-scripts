/************************************************************
SSH port forwarding
************************************************************/
# output "ssh_port_forwarding_oracle" {
#   value = <<-EOT
#     ssh -v -i ./.key/private_bastion.pem \
#     -N -L 22222:${oci_bastion_session.ssh_port_forwarding_oracle.target_resource_details[0].target_resource_private_ip_address}:22 \
#     -p 22 ${oci_bastion_session.ssh_port_forwarding_oracle.id}@host.bastion.${local.region_map["NRT"]}.oci.oraclecloud.com
#   EOT
# }

# output "ssh_command_after_ssh_port_forwarding_oracle" {
#   value = <<-EOT
#     ssh -i ./.key/private_oracle.pem \
#     -p 22222 opc@localhost
#   EOT
# }