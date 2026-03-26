/************************************************************
Dynamic Group - Compute
************************************************************/
# 「oci_identity_dynamic_group」を使用する場合はルートコンパートメントのDefaultアイデンティティドメインにしか作成できない
# 「oci_identity_domains_dynamic_resource_group」を使用すれば、指定のアイデンティティドメインに作成可能
resource "oci_identity_dynamic_group" "compute" {
  compartment_id = var.tenancy_ocid
  name           = "Compute_Dynamic_Group"
  description    = "Compute Dynamic Group"
  matching_rule = format(
    "All {instance.compartment.id = '%s', tag.Compute.CustomMetrics.value = 'true'}",
    oci_identity_compartment.workload.id
  )
  defined_tags = local.common_defined_tags
}

/************************************************************
IAM Policy - Compute
************************************************************/
resource "oci_identity_policy" "compute_for_agent_custommoni" {
  compartment_id = oci_identity_compartment.workload.id
  description    = "OCI Compute Policy for Custom Metrics Monitoring"
  name           = "compute-custom-metrics-monitoring-policy"
  statements = [
    format("allow dynamic-group %s to use metrics in compartment %s",
      oci_identity_dynamic_group.compute.name,
      oci_identity_compartment.workload.name
    )
  ]
  defined_tags = local.common_defined_tags
}