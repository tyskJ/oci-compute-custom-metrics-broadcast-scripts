#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCI Compute 上で動くカスタムメトリクス送信スクリプト（Linux / 精度重視）。
- disk: df -PT の結果から % を小数2桁で計算して送信
- procstat: ps -eo args（cmdline）に正規表現一致するプロセス数を送信
"""

# --- 標準ライブラリ（Pythonに最初から入っている）---
import argparse          # コマンドライン引数を扱う（--dry-run など）
import datetime          # 時刻（UTC）を作る
import json              # 設定ファイル（JSON）を読む/表示する
import logging           # ログ出力
import os                # 環境変数を読む（COMPARTMENT_OCID / OCI_REGION）
import re                # 正規表現（procstat の pattern 用）
import subprocess        # df / ps コマンドを実行する
import sys               # exit code（終了コード）を返す
import urllib.request    # OCI Instance Metadata(169.254.169.254)へHTTPアクセス
from typing import Any, Dict, List, Optional  # 型ヒント（読みやすさUP）

# --- OCI SDK（別途pipインストールが必要）---
try:
    import oci
    from oci.auth import signers
except Exception:
    # dry-run だけしたい場合でも落ちないように、無ければ None にする
    oci = None
    signers = None

# logger（ログの出力名）
LOG = logging.getLogger("oci_custom_agent_linux")


# -----------------------------
# Utility: Time（UTCのタイムスタンプ）
# -----------------------------
def utc_now_rfc3339() -> str:
    """
    OCI Monitoring の datapoint timestamp は RFC3339 形式が良い。
    例: 2026-03-27T09:46:29.483327+00:00
    """
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# -----------------------------
# Utility: Load Config（設定ファイルを読む）
# -----------------------------
def load_config(path: str) -> Dict[str, Any]:
    """JSON設定ファイルを読み込んで dict として返す"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -----------------------------
# OCI Metadata（Computeのメタデータからcompartment OCIDを取る）
# -----------------------------
def fetch_instance_metadata(timeout_seconds: int = 2) -> Optional[Dict[str, Any]]:
    """
    OCI Compute の Instance Metadata v2 を取得する。
    OCI上でないと失敗するので、失敗時は None を返す（例外で落とさない）
    """
    url = "http://169.254.169.254/opc/v2/instance/"
    headers = {"Authorization": "Bearer Oracle"}  # OCI IMDSv2 で必要
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        LOG.debug("metadata fetch failed: %s", e)
        return None


def get_compartment_ocid() -> str:
    """
    compartment OCID を取得する（送信時に必須）。
    取得優先度：
      1) 環境変数 COMPARTMENT_OCID（確実）
      2) OCI Instance Metadata（OCI Compute上なら取れることが多い）
    """
    env = os.environ.get("COMPARTMENT_OCID", "").strip()
    if env:
        return env

    meta = fetch_instance_metadata()
    if meta and meta.get("compartmentId"):
        return meta["compartmentId"]

    raise RuntimeError(
        "compartment OCID が取得できません。"
        "環境変数 COMPARTMENT_OCID を設定するか、OCI Compute 上で実行してください。"
    )


# -----------------------------
# Collect: Disk（ディスク％を精度重視で算出）
# -----------------------------
def collect_disks(exclude_fstypes: List[str]) -> List[Dict[str, Any]]:
    """
    df -PT で全ファイルシステムを取得し、除外fstypeを除いた結果を返す。

    精度重視：
      usage%  = used / total * 100
      avail%  = avail / total * 100
    ※ dfの「容量(%)」列は整数丸め表示なので一致しないことがある（これは仕様）
    """
    # df -P: POSIX形式でパースしやすい / -T: filesystem type を出す
    proc = subprocess.run(["df", "-PT"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"df failed: rc={proc.returncode}, stderr={proc.stderr}")

    lines = proc.stdout.strip().splitlines()
    if len(lines) <= 1:
        return []

    disks: List[Dict[str, Any]] = []
    for line in lines[1:]:
        parts = line.split()
        # 期待列：Filesystem Type 1024-blocks Used Available Capacity Mounted on
        if len(parts) < 7:
            continue

        filesystem = parts[0]
        fstype = parts[1]
        total_1k = parts[2]
        used_1k = parts[3]
        avail_1k = parts[4]
        # parts[5] は Capacity(%) だが、精度重視なので使わない
        mountpoint = " ".join(parts[6:])

        # 除外対象のfstypeはスキップ
        if fstype in exclude_fstypes:
            continue

        # 数値変換（失敗したらスキップ）
        try:
            total_kb = int(total_1k)
            used_kb = int(used_1k)
            avail_kb = int(avail_1k)
        except ValueError:
            continue
        if total_kb <= 0:
            continue

        # 小数2桁（精度重視）
        usage = round((used_kb / total_kb) * 100.0, 2)
        avail = round((avail_kb / total_kb) * 100.0, 2)

        # 念のため 0〜100 に収める（異常値対策）
        usage = max(0.0, min(100.0, usage))
        avail = max(0.0, min(100.0, avail))

        disks.append({
            "filesystem": filesystem,
            "fstype": fstype,
            "mountpoint": mountpoint,
            "usage_percent": usage,
            "available_percent": avail,
        })

    return disks


# -----------------------------
# Collect: Procstat（cmdline一致数をカウント）
# -----------------------------
def list_cmdlines() -> List[str]:
    """
    ps -eo args は、ps aux の COMMAND 相当（cmdline）を得やすい。
    例: /usr/sbin/nginx -g daemon off;
    """
    proc = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ps failed: rc={proc.returncode}, stderr={proc.stderr}")

    lines = proc.stdout.splitlines()
    # 先頭がヘッダになっている場合は除外
    if lines and lines[0].strip().lower() in ("command", "args"):
        lines = lines[1:]
    return lines


def collect_procstat(proc_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    config の procstat ルールを元に、pattern（正規表現）に一致する行数を数える。
    ※ config 側の "dimention" typo も吸収（dimensionとして扱う）
    """
    cmdlines = list_cmdlines()
    results: List[Dict[str, Any]] = []

    for rule in proc_rules:
        pattern = (rule.get("pattern") or "").strip()
        if not pattern:
            continue

        # "dimention" typo を吸収
        dim = (rule.get("dimension") or rule.get("dimention") or "unknown").strip() or "unknown"

        # 正規表現としてコンパイル（不正なら例外で気づけるようにする）
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise RuntimeError(f"invalid regex for procstat: {pattern} ({e})")

        # 1行ずつ search で一致したらカウント
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
# OCI Monitoring: Metric payload（送信形式を作る）
# -----------------------------
def build_metric_payload(
    metric_name: str,
    value: float,
    dimensions: Dict[str, str],
    timestamp: str,
    resource_group: str
) -> Dict[str, Any]:
    """
    put_metric_data へ渡す metric_data 1件分の dict を作る。
    - name: メトリクス名（例: disk_usage_percent）
    - dimensions: グルーピング用ラベル（例: mountpoint=/）
    - datapoints: timestamp と value の組
    - resource_group: OCI側で分類に使える文字列
    """
    return {
        "name": metric_name,
        "dimensions": dimensions,
        "datapoints": [{"timestamp": timestamp, "value": value}],
        "resource_group": resource_group
    }


def post_metrics_to_oci(compartment_id: str, namespace: str, metric_data: List[Dict[str, Any]]) -> None:
    """
    OCI Monitoring にメトリクスを送る。
    Instance Principals を使うので、Compute上で動かすのが前提。
    """
    if oci is None or signers is None:
        raise RuntimeError("OCI SDK がありません。pip で oci をインストールしてください。")

    # Instance Principals（Computeに割り当てた権限で認証）
    signer = signers.InstancePrincipalsSecurityTokenSigner()

    # 環境変数 OCI_REGION があれば明示（無くても動くケースは多い）
    region = os.environ.get("OCI_REGION", "").strip()
    client = oci.monitoring.MonitoringClient(config={"region": region} if region else {}, signer=signer)

    # put_metric_data に渡す詳細（compartment / namespace / metrics）
    details = oci.monitoring.models.PutMetricDataDetails(
        compartment_id=compartment_id,
        namespace=namespace,
        metric_data=metric_data
    )

    resp = client.put_metric_data(details)
    LOG.info("put_metric_data status=%s", resp.status)

    # 失敗メトリクスがあれば警告ログ
    try:
        failed = getattr(resp.data, "failed_metrics", None)
        if failed:
            LOG.warning("failed_metrics=%s", failed)
    except Exception:
        pass


# -----------------------------
# Main（ここから処理の流れが始まる）
# -----------------------------
def main() -> int:
    # 引数（configパス・dry-run・verbose）を定義
    parser = argparse.ArgumentParser(description="Collect disk/proc metrics and push to OCI Monitoring.")
    parser.add_argument("-c", "--config", default="/etc/sysconfig/oci-custom-agent-linux", help="config json path")
    parser.add_argument("--dry-run", action="store_true", help="collect only (do not post to OCI).")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose log")
    args = parser.parse_args()

    # ログ出力（-v なら DEBUG まで出す）
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # 設定読み込み
    cfg = load_config(args.config)

    # agent 設定（namespace / resource_group）
    agent = cfg.get("agent", {})
    namespace = str(agent.get("namespace", "custom_oracle_linux"))
    resource_group = str(agent.get("resource_group", "os"))

    # 収集時刻（UTC）
    ts = utc_now_rfc3339()

    # ---- disk 収集
    disk_cfg = cfg.get("disk", {})
    exclude_fstypes = disk_cfg.get("exclude_fstypes", []) or []
    disks = collect_disks(exclude_fstypes)

    # ---- procstat 収集
    proc_rules = cfg.get("procstat", []) or []
    procs = collect_procstat(proc_rules)

    # ---- 送信用のメトリクス配列を組み立て
    metric_data: List[Dict[str, Any]] = []

    # disk: mountpoint / fstype を dimensions に入れて送る
    for d in disks:
        dims = {"mountpoint": d["mountpoint"], "fstype": d["fstype"]}

        metric_data.append(build_metric_payload(
            "disk_usage_percent", float(d["usage_percent"]), dims, ts, resource_group
        ))
        metric_data.append(build_metric_payload(
            "disk_available_percent", float(d["available_percent"]), dims, ts, resource_group
        ))

    # proc: dimension を dimensions に入れて送る
    for p in procs:
        dims = {"dimension": p["dimension"]}
        metric_data.append(build_metric_payload(
            "process_count", float(p["process_count"]), dims, ts, resource_group
        ))

    # dry-run: 送信せずJSON表示して終了（動作確認用）
    if args.dry_run:
        print(json.dumps({
            "timestamp": ts,
            "namespace": namespace,
            "resource_group": resource_group,
            "metric_count": len(metric_data),
            "metric_data": metric_data,
        }, ensure_ascii=False, indent=2))
        return 0

    # 実送信：compartment OCID を取得して OCI Monitoring に送る
    compartment_id = get_compartment_ocid()
    post_metrics_to_oci(compartment_id, namespace, metric_data)
    return 0


if __name__ == "__main__":
    # 例外をログに出して終了コード1で落とす（運用時に原因が追いやすい）
    try:
        sys.exit(main())
    except Exception as e:
        LOG.exception("fatal: %s", e)
        sys.exit(1)