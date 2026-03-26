/************************************************************
Private Key
************************************************************/
resource "tls_private_key" "ssh_keygen_bastion" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "local_sensitive_file" "private_key_bastion" {
  filename        = "./.key/private_bastion.pem"
  content         = tls_private_key.ssh_keygen_bastion.private_key_pem
  file_permission = "0600"
}

/************************************************************
Public Key
************************************************************/
resource "local_sensitive_file" "public_key_bastion" {
  filename        = "./.key/public_bastion.pub"
  content         = tls_private_key.ssh_keygen_bastion.public_key_openssh
  file_permission = "0600"
}

/************************************************************
Bastion
************************************************************/
resource "oci_bastion_bastion" "this" {
  name                         = "bastion"
  compartment_id               = oci_identity_compartment.workload.id
  bastion_type                 = "STANDARD"
  target_subnet_id             = oci_core_subnet.private_bastion.id
  dns_proxy_status             = "ENABLED" # Flag to enable FQDN and SOCKS5 Proxy Support.
  client_cidr_block_allow_list = [var.source_ip]
  max_session_ttl_in_seconds   = 10800 # Max minutes (3 hours)
  defined_tags                 = local.common_defined_tags
}

/************************************************************
Session
************************************************************/
##### SSH port forwarding - Linux
# data "oci_core_instance" "oracle" {
#   instance_id = oci_core_instance.oracle_instance.id
# }

# resource "oci_bastion_session" "ssh_port_forwarding_oracle" {
#   # # ターゲットリソースがRUNNINGでないと作成不可のためcountで制御
#   # # 作成のタイミングで、Private Endpointからのインバウンドルールは不要
#   # count = contains(["PROVISIONING", "STARTING", "RUNNING"], data.oci_core_instance.oracle.state) ? 1 : 0
#   display_name = "ssh-port-forwarding-session-to-oracle"
#   bastion_id   = oci_bastion_bastion.this.id
#   target_resource_details {
#     session_type                       = "PORT_FORWARDING"
#     target_resource_id                 = oci_core_instance.oracle_instance.id
#     target_resource_port               = 22
#     target_resource_private_ip_address = oci_core_instance.oracle_instance.private_ip
#   }
#   session_ttl_in_seconds = 10800 # minutes (Max)
#   key_type               = "PUB"
#   key_details {
#     public_key_content = tls_private_key.ssh_keygen_bastion.public_key_openssh
#   }
# }

##### SSH port forwarding - Windows
# data "oci_core_instance" "windows" {
#   instance_id = oci_core_instance.windows_instance.id
# }

# resource "oci_bastion_session" "ssh_port_forwarding_windows" {
#   # # ターゲットリソースがRUNNINGでないと作成不可のためcountで制御
#   # # 作成のタイミングで、Private Endpointからのインバウンドルールは不要
#   # count = contains(["PROVISIONING", "STARTING", "RUNNING"], data.oci_core_instance.windows.state) ? 1 : 0
#   display_name = "ssh-port-forwarding-session-to-windows"
#   bastion_id   = oci_bastion_bastion.this.id
#   target_resource_details {
#     session_type                       = "PORT_FORWARDING"
#     target_resource_id                 = oci_core_instance.windows_instance.id
#     target_resource_port               = 3389
#     target_resource_private_ip_address = oci_core_instance.windows_instance.private_ip
#   }
#   session_ttl_in_seconds = 10800 # minutes (Max)
#   key_type               = "PUB"
#   key_details {
#     public_key_content = tls_private_key.ssh_keygen_bastion.public_key_openssh
#   }
# }