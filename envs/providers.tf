terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 8.0"
    }
  }
}

provider "oci" {
  auth                = "SecurityToken"
  config_file_profile = "ADMIN"
  region              = "ap-tokyo-1"
  ignore_defined_tags = [
    "Oracle-Tags.CreatedBy",
    "Oracle-Tags.CreatedOn",
    "Common.System"
  ]
}