/************************************************************
VCN
************************************************************/
resource "oci_core_vcn" "vcn" {
  compartment_id = oci_identity_compartment.workload.id
  cidr_block     = "10.0.0.0/16"
  display_name   = "vcn"
  # 最大15文字の英数字
  # 文字から始めること
  # ハイフンとアンダースコアは使用不可
  # 後から変更不可
  dns_label    = "vcn"
  defined_tags = local.common_defined_tags
}

/************************************************************
Security List
************************************************************/
##### For Bastion
resource "oci_core_security_list" "sl_bastion" {
  compartment_id = oci_identity_compartment.workload.id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "sl-bastion"
  defined_tags   = local.common_defined_tags
  # セッションを張る際は、Bastion Private Endpoint が送信元となる
  # Bastion Private Endpoint がターゲットリソースと同一サブネットでも、許可する必要がある点注意
  # Bastion Private Endpoint は NSG で制御できないので、SL での制御が必要
  egress_security_rules {
    protocol         = "6"
    description      = "Connect to SSH"
    destination      = "10.0.2.0/24"
    stateless        = false
    destination_type = "CIDR_BLOCK"
    tcp_options {
      min = 22
      max = 22
    }
  }
  egress_security_rules {
    protocol         = "6"
    description      = "Connect to RDP"
    destination      = "10.0.2.0/24"
    stateless        = false
    destination_type = "CIDR_BLOCK"
    tcp_options {
      min = 3389
      max = 3389
    }
  }
}

##### For System
resource "oci_core_security_list" "sl_system" {
  compartment_id = oci_identity_compartment.workload.id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "sl-system"
  defined_tags   = local.common_defined_tags
}

/************************************************************
Subnet
************************************************************/
### For Bastion
resource "oci_core_subnet" "private_bastion" {
  compartment_id = oci_identity_compartment.workload.id
  vcn_id         = oci_core_vcn.vcn.id
  cidr_block     = "10.0.1.0/24"
  display_name   = "private-bastion"
  # 最大15文字の英数字
  # 文字から始めること
  # ハイフンとアンダースコアは使用不可
  # 後から変更不可
  dns_label         = "bastionnw"
  security_list_ids = [oci_core_security_list.sl_bastion.id]
  # prohibit_internet_ingress と prohibit_public_ip_on_vnic は 同様の動き
  # そのため、２つのパラメータの true/false を互い違いにするとconflictでエラーとなる
  # 基本的には、値を揃えるか、どちらか一方を明記すること
  prohibit_internet_ingress  = true
  prohibit_public_ip_on_vnic = true
  defined_tags               = local.common_defined_tags
}

### For System
resource "oci_core_subnet" "private_system" {
  compartment_id = oci_identity_compartment.workload.id
  vcn_id         = oci_core_vcn.vcn.id
  cidr_block     = "10.0.2.0/24"
  display_name   = "private-system"
  # 最大15文字の英数字
  # 文字から始めること
  # ハイフンとアンダースコアは使用不可
  # 後から変更不可
  dns_label         = "systemnw"
  security_list_ids = [oci_core_security_list.sl_system.id]
  # prohibit_internet_ingress と prohibit_public_ip_on_vnic は 同様の動き
  # そのため、２つのパラメータの true/false を互い違いにするとconflictでエラーとなる
  # 基本的には、値を揃えるか、どちらか一方を明記すること
  prohibit_internet_ingress  = true
  prohibit_public_ip_on_vnic = true
  defined_tags               = local.common_defined_tags
}

/************************************************************
Service Gateway
************************************************************/
resource "oci_core_service_gateway" "service_gateway" {
  compartment_id = oci_identity_compartment.workload.id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "service-gateway"
  services {
    # All NRT Services In Oracle Services Network
    service_id = data.oci_core_services.this.services[1].id
  }
  # route_table_id = null
  defined_tags = local.common_defined_tags
}

/************************************************************
NAT Gateway
************************************************************/
resource "oci_core_nat_gateway" "nat_gateway" {
  compartment_id = oci_identity_compartment.workload.id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "nat-gateway"
  defined_tags   = local.common_defined_tags
}

/************************************************************
Route Table
************************************************************/
### For Bastion
resource "oci_core_route_table" "rtb_bastion" {
  compartment_id = oci_identity_compartment.workload.id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "rtb-bastion"
  defined_tags   = local.common_defined_tags
}

resource "oci_core_route_table_attachment" "attachment_bastion" {
  subnet_id      = oci_core_subnet.private_bastion.id
  route_table_id = oci_core_route_table.rtb_bastion.id
}

### For System
resource "oci_core_route_table" "rtb_system" {
  compartment_id = oci_identity_compartment.workload.id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "rtb-system"
  route_rules {
    network_entity_id = oci_core_service_gateway.service_gateway.id
    destination       = data.oci_core_services.this.services[1].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
  }
  route_rules {
    network_entity_id = oci_core_nat_gateway.nat_gateway.id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
  }
  defined_tags = local.common_defined_tags
}

resource "oci_core_route_table_attachment" "attachment_system" {
  subnet_id      = oci_core_subnet.private_system.id
  route_table_id = oci_core_route_table.rtb_system.id
}

/************************************************************
Network Security Group
************************************************************/
### For Oracle Linux
resource "oci_core_network_security_group" "sg_oracle" {
  compartment_id = oci_identity_compartment.workload.id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "sg-oracle"
  defined_tags   = local.common_defined_tags
}

resource "oci_core_network_security_group_security_rule" "sg_oracle_ingress_ssh" {
  network_security_group_id = oci_core_network_security_group.sg_oracle.id
  protocol                  = "6"
  direction                 = "INGRESS"
  source                    = "10.0.1.0/24"
  stateless                 = false
  source_type               = "CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_network_security_group_security_rule" "sg_oracle_egress_service_gateway" {
  network_security_group_id = oci_core_network_security_group.sg_oracle.id
  protocol                  = "6"
  direction                 = "EGRESS"
  destination               = data.oci_core_services.this.services[1].cidr_block
  stateless                 = false
  destination_type          = "SERVICE_CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_network_security_group_security_rule" "sg_oracle_egress_other" {
  network_security_group_id = oci_core_network_security_group.sg_oracle.id
  protocol                  = "all"
  direction                 = "EGRESS"
  destination               = "0.0.0.0/0"
  stateless                 = false
  destination_type          = "CIDR_BLOCK"
}

### For Windows Server
resource "oci_core_network_security_group" "sg_windows" {
  compartment_id = oci_identity_compartment.workload.id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "sg-windows"
  defined_tags   = local.common_defined_tags
}

resource "oci_core_network_security_group_security_rule" "sg_windows_ingress_rdp" {
  network_security_group_id = oci_core_network_security_group.sg_windows.id
  protocol                  = "6"
  direction                 = "INGRESS"
  source                    = "10.0.1.0/24"
  stateless                 = false
  source_type               = "CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = 3389
      max = 3389
    }
  }
}

resource "oci_core_network_security_group_security_rule" "sg_windows_egress_service_gateway" {
  network_security_group_id = oci_core_network_security_group.sg_windows.id
  protocol                  = "6"
  direction                 = "EGRESS"
  destination               = data.oci_core_services.this.services[1].cidr_block
  stateless                 = false
  destination_type          = "SERVICE_CIDR_BLOCK"
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_network_security_group_security_rule" "sg_windows_egress_other" {
  network_security_group_id = oci_core_network_security_group.sg_windows.id
  protocol                  = "all"
  direction                 = "EGRESS"
  destination               = "0.0.0.0/0"
  stateless                 = false
  destination_type          = "CIDR_BLOCK"
}