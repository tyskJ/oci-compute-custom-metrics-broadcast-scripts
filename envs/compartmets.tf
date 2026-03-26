/************************************************************
Compartment - workload
************************************************************/
resource "oci_identity_compartment" "workload" {
  compartment_id = var.tenancy_ocid
  name           = "oci-compute-custom-metrics-broadcast-scripts"
  description    = "For OCI Compute Custom Metrics Broadcast Scripts"
  enable_delete  = true
}