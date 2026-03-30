/************************************************************
Private Key
************************************************************/
resource "tls_private_key" "ssh_keygen_oracle" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "local_sensitive_file" "private_key_oracle" {
  filename        = "./.key/private_oracle.pem"
  content         = tls_private_key.ssh_keygen_oracle.private_key_pem
  file_permission = "0600"
}

/************************************************************
Compute (Oracle Linux)
************************************************************/
##### Instance
resource "oci_core_instance" "oracle_instance" {
  display_name        = "oracle-instance"
  compartment_id      = oci_identity_compartment.workload.id
  availability_domain = data.oci_identity_availability_domain.ads.name
  fault_domain        = data.oci_identity_fault_domains.fds.fault_domains[0].name
  shape               = "VM.Standard.E5.Flex"
  shape_config {
    ocpus         = 2 # ocpus * 2 vcpu
    memory_in_gbs = 8
  }
  instance_options {
    # IMDS V1 の無効化
    are_legacy_imds_endpoints_disabled = true
  }
  availability_config {
    # Live Migration の有効化
    # 無効化すると、メンテナンス時に通知がOracleから届き、手動対応が必要となる
    is_live_migration_preferred = true
    # 物理ホストメンテナンス実行後のインスタンス復旧方法
    # RESTORE_INSTCNE=再起動
    # Live Migration が有効の場合は、Live Migrationが出来なかった時に本actionが実行される
    recovery_action = "RESTORE_INSTANCE"
  }
  agent_config {
    are_all_plugins_disabled = false
    is_management_disabled   = false
    is_monitoring_disabled   = false
    plugins_config {
      desired_state = "DISABLED"
      name          = "Custom Logs Monitoring"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Compute Instance Monitoring"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Compute Instance Run Command"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Cloud Guard Workload Protection"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Block Volume Management"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Bastion"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "WebLogic Management Service"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Vulnerability Scanning"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Oracle Java Management Service"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "OS Management Hub Agent"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Management Agent"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Fleet Application Management Service"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Compute RDMA GPU Monitoring"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Compute HPC RDMA Auto-Configuration"
    }
    plugins_config {
      desired_state = "DISABLED"
      name          = "Compute HPC RDMA Authentication"
    }
  }
  create_vnic_details {
    display_name = "oracle-instance-vnic"
    subnet_id    = oci_core_subnet.private_system.id
    nsg_ids = [
      oci_core_network_security_group.sg_oracle.id
    ]
    assign_public_ip = false
    # 最大63文字 (Windowsは15文字)
    # 英数字、ハイフンは使用可
    # ピリオドは使用不可
    # 先頭 or 末尾にハイフンは使用不可
    # 数字のみになることは不可
    # RFC952 及び RFC1123 に準拠する必要有
    # 後から変更可
    hostname_label = "oracle-instance"
  }
  is_pv_encryption_in_transit_enabled = true
  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.oracle_supported_image.images[0].id
    # boot_volume_size_in_gbs         = "100"
    boot_volume_vpus_per_gb         = "10"
    is_preserve_boot_volume_enabled = false
    # kms_key_id                      = null
  }
  metadata = {
    ssh_authorized_keys = tls_private_key.ssh_keygen_oracle.public_key_openssh
    user_data           = base64encode(file("./userdata/oraclelinux_init.sh"))
  }
  defined_tags = {
    format("%s.%s", oci_identity_tag_namespace.common.name, oci_identity_tag_default.key_env.tag_definition_name)                = "prd"
    format("%s.%s", oci_identity_tag_namespace.common.name, oci_identity_tag_default.key_managedbyterraform.tag_definition_name) = "true"
    format("%s.%s", oci_identity_tag_namespace.compute.name, oci_identity_tag.key_custommetrics.name)                            = "true"
  }
  lifecycle {
    ignore_changes = [metadata]
  }
}