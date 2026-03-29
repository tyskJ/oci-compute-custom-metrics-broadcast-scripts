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

.. code-block::

  [Unit]
  Description=OCI Custom Metrics Agent

  [Service]
  User=custom_agent
  Type=oneshot
  ExecStart=/usr/bin/python3 /opt/oci-custom-metrics/oci_custom_agent_linux.py -c /etc/sysconfig/oci-custom-agent-linux

6-3. ``timer`` 自動起動有効化 & 起動
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

  systemctl enable --now oci-custom-agent-linux.timer

.. note::

  * ``systemctl list-timers`` にて表示されればOKです

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

参考資料
=====================================================================
リファレンス
---------------------------------------------------------------------
* `oci <https://docs.oracle.com/en-us/iaas/tools/python/latest/>`_

ブログ
---------------------------------------------------------------------
* `systemd.timer 入門 <https://dev.classmethod.jp/articles/slug-btThPHViGsPt/>`_