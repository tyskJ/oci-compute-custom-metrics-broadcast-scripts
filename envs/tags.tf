/************************************************************
Tag NameSpace (Compute)
************************************************************/
resource "oci_identity_tag_namespace" "compute" {
  compartment_id = oci_identity_compartment.workload.id
  name           = "Compute"
  description    = "NameSpace For Compute"
  is_retired     = false
}

resource "oci_identity_tag" "key_custommetrics" {
  tag_namespace_id = oci_identity_tag_namespace.compute.id
  name             = "CustomMetrics"
  description      = "Get Custom Metrics"
  is_cost_tracking = false
  is_retired       = false
  validator {
    validator_type = "ENUM"
    values         = ["true", "false"]
  }
}

/************************************************************
Tag NameSpace (Common)
************************************************************/
resource "oci_identity_tag_namespace" "common" {
  compartment_id = oci_identity_compartment.workload.id
  name           = "Common"
  description    = "NameSpace for Common"
  is_retired     = false
}

resource "oci_identity_tag" "key_system" {
  tag_namespace_id = oci_identity_tag_namespace.common.id
  name             = "System"
  description      = "Defined System"
  is_cost_tracking = true
  is_retired       = false
}

resource "oci_identity_tag" "key_env" {
  tag_namespace_id = oci_identity_tag_namespace.common.id
  name             = "Env"
  description      = "Defined Environment"
  is_cost_tracking = true
  is_retired       = false
  validator {
    validator_type = "ENUM"
    values         = ["prd", "dev"]
  }
}

resource "oci_identity_tag" "key_managedbyterraform" {
  tag_namespace_id = oci_identity_tag_namespace.common.id
  name             = "ManagedByTerraform"
  description      = "Defined Managed By Terraform"
  is_cost_tracking = true
  is_retired       = false
  validator {
    validator_type = "ENUM"
    values         = ["true", "false"]
  }
}

/************************************************************
Default Tag
************************************************************/
resource "oci_identity_tag_default" "key_system" {
  compartment_id    = oci_identity_compartment.workload.id
  tag_definition_id = oci_identity_tag.key_system.id
  value             = "oci-compute-custom-metrics-broadcast-scripts"
  # TagがENUMでなく、値を固定しているためfalse
  # リソース作成時に自動的に設定されるためfalse
  # →trueにして、リソース作成時に強制明記させる必要がない
  is_required = false
}

resource "oci_identity_tag_default" "key_env" {
  compartment_id    = oci_identity_compartment.workload.id
  tag_definition_id = oci_identity_tag.key_env.id
  value             = "prd"
  is_required       = true
}

resource "oci_identity_tag_default" "key_managedbyterraform" {
  compartment_id    = oci_identity_compartment.workload.id
  tag_definition_id = oci_identity_tag.key_managedbyterraform.id
  value             = "true"
  is_required       = true
}