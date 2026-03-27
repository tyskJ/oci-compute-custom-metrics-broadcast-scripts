#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCI Compute 上で動作させることを想定したカスタムメトリクス送信スクリプト。

- disk: df -PT で取得できるファイルシステムを対象（exclude_fstypes は除外）
- procstat: ps -eo args の cmdline に対して pattern(正規表現) で一致したプロセス数を送信

要件:
- OCI Python SDK (oci) が必要
- 認証は Instance Principals を優先
- compartment OCID は以下の優先順で取得
    1) 環境変数 COMPARTMENT_OCID
    2) OCI Instance Metadata から取得（OCI上でのみ有効）
"""

import argparse
import datetime
import json
import logging
import os
import re
import subprocess
import sys
import urllib.request
from typing import Any, Dict, List, Optional

try:
    import oci
    from oci.auth import signers
except Exception as e:
    oci = None
    signers = None


LOG = logging.getLogger("linux_custom_metrics")


# -----------------------------
# Utility: Time
# -----------------------------
def utc_now_rfc3339() -> str:
    # OCI Monitoring datapoint timestamp: RFC3339
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# -----------------------------
# Utility: Load Config
# -----------------------------
def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -----------------------------
# OCI Metadata (for compartment id)
# -----------------------------
def fetch_instance_metadata(timeout_seconds: int = 2) -> Optional[Dict[str, Any]]:
    """
    OCI Instance Metadata v2 を取得。
    OCI 上以外では失敗するので例外は握りつぶして None を返す。
    """
    url = "http://169.254.169.254/opc/v2/instance/"
    headers = {"Authorization": "Bearer Oracle"}  # required for IMDSv2
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except Exception as e:
        LOG.debug("metadata fetch failed: %s", e)
        return None


def get_compartment_ocid(cfg: Dict[str, Any]) -> str:
    """
    compartment OCID を取得（必須）。
    - env: COMPARTMENT_OCID
    - metadata: compartmentId
    """
    env = os.environ.get("COMPARTMENT_OCID", "").strip()
    if env:
        return env

    meta = fetch_instance_metadata()
    if meta and isinstance(meta, dict) and meta.get("compartmentId"):
        return meta["compartmentId"]

    raise RuntimeError(
        "compartment OCID が取得できません。"
        "環境変数 COMPARTMENT_OCID を設定するか、OCI Compute 上で実行してください。"
    )


# -----------------------------
# Collect: Disk
# -----------------------------
def collect_disks(exclude_fstypes: List[str]) -> List[Dict[str, Any]]:
    """
    df -PT の出力をパースし、fstype が除外対象でないものを返す。
    df の used/avail は通常 1K-blocks 基準の数値（-P で安定）
    """
    cmd = ["df", "-PT"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if proc.returncode != 0:
        raise RuntimeError(f"df command failed: rc={proc.returncode}, stderr={proc.stderr}")

    lines = proc.stdout.strip().splitlines()
    if len(lines) <= 1:
        return []

    # header: Filesystem Type 1024-blocks Used Available Capacity Mounted on
    disks = []
    for line in lines[1:]:
        # mountpoint に空白が入るケースは通常少ないが、
        # 念のため split の結果が多い場合は末尾を mount とする
        parts = line.split()
        if len(parts) < 7:
            continue

        filesystem = parts[0]
        fstype = parts[1]
        blocks_1k = parts[2]
        used_1k = parts[3]
        avail_1k = parts[4]
        capacity = parts[5]       # "12%"
        mountpoint = " ".join(parts[6:])

        if fstype in exclude_fstypes:
            continue

        # 数値変換
        try:
            used_kb = int(used_1k)
            avail_kb = int(avail_1k)
            usage_percent = int(capacity.rstrip("%"))
        except ValueError:
            continue

        disks.append({
            "filesystem": filesystem,
            "fstype": fstype,
            "mountpoint": mountpoint,
            "usage_percent": usage_percent,
            "used_bytes": used_kb * 1024,
            "available_bytes": avail_kb * 1024,
        })

    return disks


# -----------------------------
# Collect: Procstat
# -----------------------------
def list_cmdlines() -> List[str]:
    """
    ps aux の COMMAND 相当を狙うなら、ps -eo args が一番シンプル。
    """
    cmd = ["ps", "-eo", "args"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ps command failed: rc={proc.returncode}, stderr={proc.stderr}")

    lines = proc.stdout.splitlines()
    # 先頭行は "COMMAND" 的なヘッダになる場合があるので除外
    if lines and lines[0].strip().lower() in ("command", "args"):
        lines = lines[1:]
    return lines


def collect_procstat(proc_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    procstat のルールに従って、cmdline に正規表現一致した件数を返す。
    config 側のキーは dimension/dimention どちらでも許容。
    """
    cmdlines = list_cmdlines()
    results = []

    for rule in proc_rules:
        pattern = (rule.get("pattern") or "").strip()
        if not pattern:
            continue

        # dimensionキーは、ユーザー入力の "dimention" typo にも対応
        dim = (rule.get("dimension") or rule.get("dimention") or "unknown").strip()
        if not dim:
            dim = "unknown"

        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise RuntimeError(f"invalid regex pattern for procstat: {pattern} ({e})")

        count = 0
        for cmdline in cmdlines:
            if regex.search(cmdline):
                count += 1

        results.append({
            "dimension": dim,
            "pattern": pattern,
            "process_count": count
        })

    return results


# -----------------------------
# OCI Monitoring: Post metrics
# -----------------------------
def build_metric_payload(
    namespace: str,
    resource_group: str,
    metric_name: str,
    value: float,
    dimensions: Dict[str, str],
    timestamp: str
) -> Dict[str, Any]:
    """
    PutMetricDataDetails の metricData 要素を dict で組み立てる。
    SDK にそのまま渡せる形。
    """
    return {
        "name": metric_name,
        "dimensions": dimensions,
        "datapoints": [
            {"timestamp": timestamp, "value": value}
        ],
        "resource_group": resource_group
    }


def post_metrics_to_oci(
    compartment_id: str,
    namespace: str,
    resource_group: str,
    metric_data: List[Dict[str, Any]]
) -> None:
    """
    OCI Monitoring へメトリクス投入。
    Instance Principals を使用。
    """
    if oci is None or signers is None:
        raise RuntimeError("OCI Python SDK (oci) が import できません。pip で oci を入れてください。")

    signer = signers.InstancePrincipalsSecurityTokenSigner()

    # region は signer が内部で解決するが、環境によっては明示が必要な場合がある。
    # その場合は OCI_REGION を設定するとよい（例: ap-tokyo-1）
    region = os.environ.get("OCI_REGION", "").strip()
    if region:
        config = {"region": region}
        client = oci.monitoring.MonitoringClient(config=config, signer=signer)
    else:
        client = oci.monitoring.MonitoringClient(config={}, signer=signer)

    details = oci.monitoring.models.PutMetricDataDetails(
        compartment_id=compartment_id,
        namespace=namespace,
        metric_data=metric_data
    )

    resp = client.put_metric_data(details)
    # 成功/失敗の詳細は resp.data で見れる
    LOG.info("put_metric_data status=%s, failed_count=%s",
             resp.status, getattr(resp.data, "failed_metrics", None))


# -----------------------------
# Main
# -----------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Collect disk/proc metrics and push to OCI Monitoring.")
    parser.add_argument(
        "-c", "--config",
        default="/etc/sysconfig/oci-custom-agent-linux",
        help="config json path"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="collect only (do not post to OCI). print metrics to stdout."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="verbose log"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    cfg = load_config(args.config)

    agent = cfg.get("agent", {})
    interval_seconds = int(agent.get("interval_seconds", 60))
    namespace = str(agent.get("namespace", "custom_oracle_linux"))
    resource_group = str(agent.get("resource_group", "os"))

    # timestamp は収集時点（1分毎実行を想定）
    ts = utc_now_rfc3339()

    # ---- collect disk
    disk_cfg = cfg.get("disk", {})
    exclude_fstypes = disk_cfg.get("exclude_fstypes", []) or []
    disks = collect_disks(exclude_fstypes)

    # ---- collect procstat
    proc_rules = cfg.get("procstat", []) or []
    procs = collect_procstat(proc_rules)

    # ---- build metric data
    metric_data = []

    # Disk metrics: mountpoint を dimension にする
    for d in disks:
        dims = {
            "mountpoint": d["mountpoint"],
            "fstype": d["fstype"],
        }
        metric_data.append(build_metric_payload(
            namespace, resource_group,
            "disk_usage_percent", float(d["usage_percent"]),
            dims, ts
        ))
        metric_data.append(build_metric_payload(
            namespace, resource_group,
            "disk_used_bytes", float(d["used_bytes"]),
            dims, ts
        ))
        metric_data.append(build_metric_payload(
            namespace, resource_group,
            "disk_available_bytes", float(d["available_bytes"]),
            dims, ts
        ))

    # Proc metrics: dimension(=dimention) を dimension として送る
    for p in procs:
        dims = {"dimension": p["dimension"]}
        metric_data.append(build_metric_payload(
            namespace, resource_group,
            "process_count", float(p["process_count"]),
            dims, ts
        ))

    if args.dry_run:
        # 送信せずに内容表示
        out = {
            "timestamp": ts,
            "namespace": namespace,
            "resource_group": resource_group,
            "interval_seconds": interval_seconds,
            "metric_count": len(metric_data),
            "metric_data": metric_data,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # ---- post to OCI
    compartment_id = get_compartment_ocid(cfg)
    post_metrics_to_oci(compartment_id, namespace, resource_group, metric_data)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        LOG.exception("fatal: %s", e)
        sys.exit(1)
``