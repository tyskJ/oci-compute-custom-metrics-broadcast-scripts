# フォルダ構成

- フォルダ構成は以下の通り

```
.
└── envs
    ├── backend.tf                              tfstateファイル管理定義ファイル
    ├── bastion.tf                              Bastion定義ファイル
    ├── compartments.tf                         デプロイ用コンパートメント定義ファイル
    ├── compute_linux.tf                        OCI compute(Oracle Linux)定義ファイル
    ├── compute_windows.tf                      OCI compute(Windows Server)定義ファイル
    ├── config
    │   ├── linux
    │   │   ├── oci-custom-agent-linux.json     スクリプトに読み込ませる設定ファイル     
    │   │   └── oci_custom_agent_linux.py       メトリクス取得スクリプト
    │   └── windows
    │       ├── oci-custom-agent-windows.json   スクリプトに読み込ませる設定ファイル
    │       └── oci_custom_agent_windows.py     メトリクス取得スクリプト
    ├── data.tf                                 外部データソース定義ファイル
    ├── iam.tf                                  IAM定義ファイル
    ├── locals.tf                               ローカル変数定義ファイル
    ├── outputs.tf                              リソース戻り値定義ファイル
    ├── providers.tf                            プロバイダー定義ファイル
    ├── tags.tf                                 デフォルトタグ定義ファイル
    ├── userdata
    │   ├── oraclelinux_init.sh                 Linux用userdataスクリプト
    │   └── windows_init.ps1                    Windows用userdataスクリプト
    ├── variables.tf                            変数定義ファイル
    ├── vcn.tf                                  VCN定義ファイル
    └── versions.tf                             Terraformバージョン定義ファイル
```