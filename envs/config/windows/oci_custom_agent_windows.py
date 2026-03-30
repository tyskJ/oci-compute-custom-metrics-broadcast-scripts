#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCI Compute 上で動くカスタムメトリクス送信スクリプト（Windows / 精度重視）。
- disk:
    - 設定ファイル disk.drive_letters に書かれたドライブのみ対象
    - Win32_LogicalDisk の Size / FreeSpace から % を小数2桁で計算して送信
- procstat:
    - Get-WmiObject Win32_Process の CommandLine を取得し
      pattern（正規表現）で一致するプロセス数を送信
- logging:
    - 通常ログ：stdout（タスクスケジューラ等で取得）
    - ERROR以上：agent.error_log_path（任意）へ日次ローテで出力
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
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Dict, List, Optional

# --- OCI SDK（別途 pip インストールが必要）---
try:
    import oci
    from oci.auth import signers
except Exception:
    oci = None
    signers = None

LOG = logging.getLogger("oci_custom_agent_windows")

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
# Utility: Logging（ERRORだけファイルに日次ローテ）
# -----------------------------
def add_daily_error_file_handler(
    path: str, 
    backup_days: int = 14, 
    use_utc: bool = False
) -> None:
    """
    ERROR以上だけをファイルへ出し、日次でローテーションする。

    - path: /var/log/oci-custom-agent/error.log
    - backup_days: 保持日数（例: 7 / 14 / 30）
    - use_utc: TrueならUTC基準で日付を切る。JST運用なら False 推奨。

    delay=True により、エラーが発生するまでファイルを作成しない。
    """
    root = logging.getLogger()

    # 二重登録防止（念のため）
    for h in root.handlers:
        if isinstance(h, TimedRotatingFileHandler) and getattr(h, "baseFilename", "") == path:
            return

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    fh = TimedRotatingFileHandler(
        filename=path,
        when="midnight",        # 日付が変わるタイミングでローテ
        interval=1,             # 1日ごと
        backupCount=backup_days,
        encoding="utf-8",
        utc=use_utc,
        delay=True              # ★重要：エラーが出るまで error.log を作らない
    )
    fh.setLevel(logging.ERROR)  # ★ERROR以上だけファイルへ
    fh.setFormatter(fmt)
    root.addHandler(fh)

# -----------------------------
# OCI Metadata（Computeメタデータ）
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

def get_compartment_ocid(meta: Optional[Dict[str, Any]] = None) -> str:
    """
    compartment OCID を取得する（送信時に必須）。
    取得優先度：
      1) 環境変数 COMPARTMENT_OCID（確実）
      2) OCI Instance Metadata（OCI Compute上なら取れることが多い）
    """
    env = os.environ.get("COMPARTMENT_OCID", "").strip()
    if env:
        return env

    # meta が渡されていなければ、その場で取りにいく（後方互換）
    if meta is None:
        meta = fetch_instance_metadata()

    if meta and meta.get("compartmentId"):
        return meta["compartmentId"]

    raise RuntimeError(
        "compartment OCID が取得できません。"
        "環境変数 COMPARTMENT_OCID を設定するか、OCI Compute 上で実行してください。"
    )

def get_region(meta: Optional[Dict[str, Any]] = None) -> str:
    """
    OCIのリージョンを取得する
    優先順位：
      1) 環境変数 OCI_REGION
      2) Instance Metadata
    """
    env = os.environ.get("OCI_REGION", "").strip()
    if env:
        return env

    # meta が渡されていなければ、その場で取りにいく（後方互換）
    if meta is None:
        meta = fetch_instance_metadata()

    if meta:
        # region または canonicalRegionName が入っている場合がある
        region = meta.get("region") or meta.get("canonicalRegionName")
        if region:
            return region

    raise RuntimeError(
        "OCI region が取得できません。"
        "環境変数 OCI_REGION を設定するか、OCI Compute 上で実行してください。"
    )

# -----------------------------
# Utility: PowerShell 実行（JSON返却）
# -----------------------------
def run_powershell_json(
  ps_script: str, 
  timeout_seconds: int = 30
) -> Any:
    """
    PowerShell を実行して JSON を受け取り、Pythonオブジェクトにして返す。
    - UTF-8 を明示して文字化けを抑制
    - ConvertTo-Json の結果が単一オブジェクトの場合もあるので呼び出し側で吸収
    """
    # PowerShell側で出力エンコーディングをUTF-8へ寄せる（Windows PowerShell 5系対策）
    wrapper = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "[System.Text.UTF8Encoding]::new();"
        + ps_script
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", wrapper],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"powershell failed: rc={proc.returncode}, stderr={proc.stderr}")

    out = (proc.stdout or "").strip()
    if not out:
        return None

    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"powershell output is not valid JSON: {e}; output={out[:2000]}")


# -----------------------------
# Collect: Disk（対象ドライブのみ）
# -----------------------------
def normalize_drive_letters(drive_letters: List[str]) -> List[str]:
    """
    ["c","D","e:"] などを ["C:","D:","E:"] に正規化
    """
    result = []
    for d in drive_letters or []:
        s = str(d).strip()
        if not s:
            continue
        s = s.replace("\\", "").replace("/", "")
        s = s.upper()
        if len(s) == 1:
            s = s + ":"
        if len(s) >= 2 and s[1] == ":":
            result.append(s[:2])
    # 重複排除（順序維持）
    seen = set()
    out = []
    for x in result:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def collect_disks(drive_letters: List[str]) -> List[Dict[str, Any]]:
    """
    Win32_LogicalDisk から Size / FreeSpace を取得して % を算出する。
    usage%  = (size - free) / size * 100
    avail%  = free / size * 100
    """
    drives = normalize_drive_letters(drive_letters)
    if not drives:
        return []

    disks: List[Dict[str, Any]] = []
    for drive in drives:
        # DriveType=3 はローカルディスク
        ps = (
            f"$d = Get-CimInstance Win32_LogicalDisk "
            f"-Filter \"DeviceID='{drive}' AND DriveType=3\" | "
            f"Select-Object DeviceID, Size, FreeSpace; "
            f"$d | ConvertTo-Json -Compress"
        )
        obj = run_powershell_json(ps)
        if not obj:
            continue  # 存在しない/取得不可はスキップ

        # ConvertTo-Json は単一オブジェクトなら dict、複数なら list（ここでは単一想定）
        if isinstance(obj, list):
            if not obj:
                continue
            obj = obj[0]

        try:
            size = int(obj.get("Size") or 0)
            free = int(obj.get("FreeSpace") or 0)
        except Exception:
            continue
        if size <= 0:
            continue

        used = size - free
        usage = round((used / size) * 100.0, 2)
        avail = round((free / size) * 100.0, 2)

        usage = max(0.0, min(100.0, usage))
        avail = max(0.0, min(100.0, avail))

        disks.append({
            "drive": drive,
            "size_bytes": size,
            "free_bytes": free,
            "usage_percent": usage,
            "available_percent": avail,
        })

    return disks


# -----------------------------
# Collect: Procstat（CommandLine regex一致数）
# -----------------------------
def list_cmdlines() -> List[str]:
    """
    Get-WmiObject -Class Win32_Process | Select-Object CommandLine の結果から
    CommandLine（nullを除く）を配列で返す。
    """
    ps = (
        "Get-WmiObject -Class Win32_Process | "
        "Select-Object -ExpandProperty CommandLine | "
        "Where-Object { $_ -ne $null -and $_ -ne '' } | "
        "ConvertTo-Json -Compress"
    )
    obj = run_powershell_json(ps)

    if obj is None:
        return []

    # 1件だけだと文字列、複数だと list になるので吸収
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, list):
        # 念のため文字列以外は除外
        return [x for x in obj if isinstance(x, str)]
    return []


def collect_procstat(proc_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cmdlines = list_cmdlines()
    results: List[Dict[str, Any]] = []

    for rule in proc_rules or []:
        pattern = (rule.get("pattern") or "").strip()
        if not pattern:
            continue

        dim = (rule.get("name") or "unknown").strip() or "unknown"

        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise RuntimeError(f"invalid regex for procstat: {pattern} ({e})")

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
# OCI Monitoring: Metric payload
# -----------------------------
def build_metric_payload(
    metric_name: str,
    namespace: str,
    resource_group: str,
    compartment_id: str,
    dimensions: Dict[str, str],
    timestamp: str,
    value: float,
) -> Dict[str, Any]:
    """
    put_metric_data へ渡す metric_data 1件分の dict を作る。
    - name: メトリクス名（例: disk_usage_percent）
    - namespace: リソース識別子
    - resource_group: OCI側で分類に使える文字列
    - compartment_id: メトリクスをプッシュするコンパートメントのOCID
    - dimensions: グルーピング用ラベル（例: mountpoint=/）
    - datapoints: timestamp と value の組
    """
    metric_detail = oci.monitoring.models.MetricDataDetails(
        name = metric_name,
        namespace = namespace,
        resource_group = resource_group,
        compartment_id = compartment_id,
        dimensions = dimensions,
        datapoints = [
            oci.monitoring.models.Datapoint(
                timestamp = timestamp,
                value = value
            )
        ]
    )
    return metric_detail


def post_metrics_to_oci(
    metric_data: List[Dict[str, Any]],
    meta: Optional[Dict[str, Any]] = None
) -> None:
    """
    OCI Monitoring にメトリクスを送る。
    Instance Principals を使うので、Compute上で動かすのが前提。
    """
    if oci is None or signers is None:
        raise RuntimeError("OCI SDK がありません。pip で oci をインストールしてください。")

    # Instance Principals（Computeに割り当てた権限で認証）
    signer = signers.InstancePrincipalsSecurityTokenSigner()

    # 環境変数 OCI_REGION があれば明示（無くても動くケースは多い）
    region = get_region(meta)
    service_endpoint = f"https://telemetry-ingestion.{region}.oraclecloud.com"
    client = oci.monitoring.MonitoringClient(
        config={"region": region} if region else {}, 
        signer=signer, 
        service_endpoint=service_endpoint
    )

    # put_metric_data に渡すデータポイントの詳細
    details = oci.monitoring.models.PostMetricDataDetails(
        metric_data = metric_data
    )

    # メトリクスをプッシュ
    resp = client.post_metric_data(details)
    LOG.info("put_metric_data status=%s", resp.status)

    # 失敗メトリクスがあれば警告ログ
    try:
        failed = getattr(resp.data, "failed_metrics", None)
        if failed:
            LOG.warning("failed_metrics=%s", failed)
    except Exception:
        pass

# -----------------------------
# Main
# -----------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Collect disk/proc metrics and push to OCI Monitoring (Windows).")
    parser.add_argument("-c", "--config", default=r"C:\ProgramData\oci-custom-agent\oci-custom-agent-windows.json", help="config json path")
    parser.add_argument("--dry-run", action="store_true", help="collect only (do not post to OCI).")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose log")
    args = parser.parse_args()

    # stdout向けログ初期化（タスクスケジューラ等で拾う）
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # 収集時刻（UTC）
    ts = utc_now_rfc3339()

    # 設定読み込み
    cfg = load_config(args.config)

    # agent 設定（namespace / resource_group）
    agent = cfg.get("agent", {})
    namespace = str(agent.get("namespace", "custom_windows_server"))
    resource_group = str(agent.get("resource_group", "os"))

    # 任意：ERRORログをファイルにも（設定があれば）
    error_log_path = str(agent.get("error_log_path", "")).strip()
    error_log_backup_days = int(agent.get("error_log_backup_days", 7))
    error_log_use_utc = bool(agent.get("error_log_use_utc", False))

    if error_log_path:
        add_daily_error_file_handler(
            path=error_log_path,
            backup_days=error_log_backup_days,
            use_utc=error_log_use_utc
        )
        LOG.info(
            "error log enabled: path=%s (daily rotation, keep=%d days, utc=%s)",
            error_log_path, error_log_backup_days, error_log_use_utc
        )
    else:
        LOG.info("error log disabled (agent.error_log_path is empty)")

    # Instance Metadata はここで 1回だけ取得して使い回す
    meta = fetch_instance_metadata()

    # compartment / region をメタデータ使い回しで取得
    compartment_id = get_compartment_ocid(meta)


    # ---- disk 収集
    disk_cfg = cfg.get("disk", {})
    drive_letters = disk_cfg.get("drive_letters", []) or []
    disks = collect_disks(drive_letters)

    # ---- procstat 収集
    proc_rules = cfg.get("procstat", []) or []
    procs = collect_procstat(proc_rules)

    # ---- 送信用のメトリクス配列を組み立て
    metric_data: List[Dict[str, Any]] = []

    for d in disks:
        dims = {"drive": d["drive"]}
        metric_data.append(build_metric_payload(
            "disk_usage_percent", namespace, resource_group, compartment_id, dims, ts, float(d["usage_percent"])
        ))
        metric_data.append(build_metric_payload(
            "disk_available_percent", namespace, resource_group, compartment_id, dims, ts, float(d["available_percent"])
        ))

    for p in procs:
        dims = {"name": p["dimension"]}
        metric_data.append(build_metric_payload(
            "process_count", namespace, resource_group, compartment_id, dims, ts, float(p["process_count"])
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
    post_metrics_to_oci(metric_data, meta)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        LOG.exception("fatal: %s", e)
        sys.exit(1)