Linux
=====================================================================
.. note::

  * ``root`` ユーザーにて実行します

1. ``Python`` & ``pip`` インストール
---------------------------------------------------------------------
.. code-block:: bash

  dnf install -y python3
  dnf install -y python3-pip

.. note::

  * ``python3 --version`` , ``pip3 --version`` でそれぞれバージョンが表示されればOK

2. 必要パッケージインストール
---------------------------------------------------------------------
.. code-block:: bash

  pip3 install --upgrade pip --root-user-action=ignore
  pip3 install oci --root-user-action=ignore

.. note::
  
  以下コマンドを実行して ``successfully`` がでればOK

.. code-block:: bash

  python3 - <<'EOF'
  import oci
  print("oci imported successfully")
  EOF

.. note::

  以下コマンドでインストール先が確認できます

.. code-block:: bash

  python3 - <<'EOF'
  import oci
  print(oci.__file__)
  EOF

3. 専用システムユーザー作成
---------------------------------------------------------------------
.. code-block:: bash

  useradd -s /sbin/nologin -M custom_agent

4. 設定ファイル作成
---------------------------------------------------------------------
`/etc/sysconfig/oci-custom-agent-linux <./envs/config/linux/oci-custom-agent-linux.json>`_

.. code-block:: bash

  chown root:custom_agent /etc/sysconfig/oci-custom-agent-linux
  chmod 640 /etc/sysconfig/oci-custom-agent-linux

5. スクリプトファイル作成
---------------------------------------------------------------------
.. code-block:: bash

  mkdir -p /opt/oci-custom-metrics
  
`/opt/oci-custom-metrics/oci_custom_agent_linux.py <./envs/config/linux/oci_custom_agent_linux.py>`_

.. code-block:: bash

  chown root:custom_agent /opt/oci-custom-metrics/oci_custom_agent_linux.py
  chmod 640 /opt/oci-custom-metrics/oci_custom_agent_linux.py

6. 定期実行設定
---------------------------------------------------------------------
6-1. ``systemd.timer`` 設定
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**/etc/systemd/system/oci-custom-agent-linux.timer**

.. code-block:: bash

  [Unit]
  Description=Run OCI Custom Metrics Agent every minute

  [Timer]
  OnBootSec=3m
  OnUnitActiveSec=1m
  AccuracySec=100ms
  Unit=oci-custom-agent-linux.service

  [Install]
  WantedBy=timers.target

6-2. ``systemd.service`` 設定
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**/etc/systemd/system/oci-custom-agent-linux.service**

.. code-block:: bash

  [Unit]
  Description=OCI Custom Metrics Agent

  [Service]
  Type=oneshot
  User=custom_agent
  Group=custom_agent
  # journald に通常ログを出す
  StandardOutput=journal
  StandardError=journal
  # /var/log/oci-custom-agent を systemd が作る（権限事故防止）
  LogsDirectory=oci-custom-agent
  # 作成時のパーミッション（必要なら調整）
  LogsDirectoryMode=0750
  # 実行
  ExecStart=/usr/bin/python3 /opt/oci-custom-metrics/oci_custom_agent_linux.py -c /etc/sysconfig/oci-custom-agent-linux
  # セキュリティ/事故防止（任意だがおすすめ）
  NoNewPrivileges=true
  PrivateTmp=true
  # 作られるログファイル権限を絞る（例：0640）
  UMask=0027


6-3. ``timer`` 自動起動有効化 & 起動
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

  systemctl enable --now oci-custom-agent-linux.timer

.. note::

  * ``systemctl list-timers`` にて表示されればOKです

6-4. 実行確認
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

  journalctl -u oci-custom-agent-linux.timer
  journalctl -u oci-custom-agent-linux.service

Windows
=====================================================================
1. ``Python Install Manager`` インストール
---------------------------------------------------------------------
* `公式 <https://www.python.org/downloads/windows/>`_ より最新のインストーラー (``MSI package``) をダウンロード
* ``msi`` ファイルを実行してインストール

2. ``Python 3`` インストール - 最新版 -
---------------------------------------------------------------------
.. code-block:: powershell

  py install 3

.. note:: 

  * ``python3 --version`` でバージョンが表示されればOKです

3. ``pip3`` への ``PATH`` を通す
---------------------------------------------------------------------
* 下記コマンドを実行し、グローバルショートカット用ディレクトリを取得

.. code-block:: powershell

  py isntall --refresh

* 下記コマンドを ``Powershell`` で実行し、システムプロパティを起動
* 環境変数のシステム変数に上記コマンドで出力されたディレクトリを追加

.. code-block:: powershell

  SystemPropertiesAdvanced

.. note::

  * ターミナルを再起動し、``pip3 --version`` でバージョンが表示されればOKです

4. 必要パッケージインストール
---------------------------------------------------------------------
.. code-block:: powershell

  pip3 install --upgrade pip --root-user-action=ignore
  pip3 install oci --root-user-action=ignore

.. note::
  
  以下コマンドを実行して ``successfully`` がでればOK

.. code-block:: powershell

  @'
  import oci
  print("oci imported successfully")
  '@ | python3 -

.. note::

  以下コマンドでインストール先が確認できます

.. code-block:: bash

  @'
  import oci
  print(oci.__file__)
  '@ | python3 -

5. 設定ファイル & スクリプトファイル作成
---------------------------------------------------------------------

.. note::

  * 管理者権限で ``Powershell`` を起動して実行します

5-1. 専用ユーザー作成
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. code-block:: powershell

  # ===== 専用ユーザー作成（ランダムPW生成して最後に表示）=====
  $User = "custom_agent"

  # ランダムパスワード生成（英大文字/小文字/数字/記号を混ぜる）
  Add-Type -AssemblyName System.Web
  $PlainPassword = [System.Web.Security.Membership]::GeneratePassword(24, 4)

  # SecureString に変換してユーザー作成
  $SecurePassword = ConvertTo-SecureString $PlainPassword -AsPlainText -Force

  New-LocalUser -Name $User `
    -Password $SecurePassword `
    -PasswordNeverExpires `
    -AccountNeverExpires `
    -Description "OCI custom metrics agent"

  Write-Host "User created: $User"
  Write-Host "Password (save securely): $PlainPassword"

.. code-block:: powershell

  Get-LocalUser -Name custom_agent | Select-Object Name, Enabled, LastLogon

5-2. 専用フォルダ作成
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. code-block:: powershell

  New-Item -ItemType Directory -Force -Path C:\ProgramData\oci-custom-agent\log | Out-Null
  New-Item -ItemType Directory -Force -Path C:\ProgramData\oci-custom-agent\config | Out-Null

.. code-block:: powershell

  # スクリプト配置フォルダ：読み取り＆実行
  icacls C:\ProgramData\oci-custom-agent /grant custom_agent:RX

  # 設定フォルダ：読み取り
  icacls C:\ProgramData\oci-custom-agent\config /grant custom_agent:R

  # ログフォルダ：書き込み（Modify）
  icacls C:\ProgramData\oci-custom-agent\log /grant custom_agent:W


5-3. 設定ファイル作成
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

`C:\ProgramData\oci-custom-agent\config\oci-custom-agent-windows.json <./envs/config/windows/oci-custom-agent-windows.json>`_

5-4. スクリプトファイル作成
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

`C:\ProgramData\oci-custom-agent\oci_custom_agent_windows.py <./envs/config/windows/oci_custom_agent_windows.py>`_

参考資料
=====================================================================
リファレンス
---------------------------------------------------------------------
* `oci <https://docs.oracle.com/en-us/iaas/tools/python/latest/>`_

ブログ
---------------------------------------------------------------------
* `systemd.timer 入門 <https://dev.classmethod.jp/articles/slug-btThPHViGsPt/>`_
* `CloudWatch Agent の procstat プラグインで exe と pattern に指定するプロセス名・プロセス起動のコマンドラインを確認する方法 - DevelopersIO <https://dev.classmethod.jp/articles/cloudwatch-agent-procstat-exe-pattern/>`_
* `CloudWatchでWindowsのプロセスを監視する - Beex Techblog <https://techblog.beex-inc.com/entry/2024/10/01/000000>`_